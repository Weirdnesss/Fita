"""
Applies predefined if-then rules to a user's structured nutrition and
workout data for a period, producing a list of typed insights plus
combined recommendations. This is the "rule-based" half of the hybrid
progress-report approach -- its output feeds into the LLM as grounding
context, so the narrative report stays anchored to real numbers rather
than the model inventing plausible-sounding feedback.
"""

# Day-to-day weight swings (water, meals, time of day) are larger than this,
# so a smaller change over the period isn't treated as a real direction.
WEIGHT_NOISE_KG = 0.3

PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


class RuleBasedAnalyzer:
    def analyze_all(self, nutrition_data, workout_data, weight_data=None):
        nutrition_insights = self._analyze_nutrition(nutrition_data)
        workout_insights = self._analyze_workout(workout_data)
        weight_insights = self._analyze_weight(weight_data or {"has_data": False})
        return {
            "nutrition_insights": nutrition_insights,
            "workout_insights": workout_insights,
            "weight_insights": weight_insights,
            "overall_recommendations": self._combine_recommendations(
                nutrition_insights, workout_insights, weight_insights
            ),
        }

    def _analyze_nutrition(self, data):
        if not data.get("has_data"):
            return {"status": "insufficient_data", "insights": []}

        insights = []
        adherence = data["adherence"]
        overall = adherence["overall"]

        if overall >= 90:
            insights.append({"type": "excellent", "message": "Exceptional nutrition adherence -- consistently meeting goals."})
        elif overall >= 75:
            insights.append({"type": "good", "message": "Strong nutrition adherence -- minor adjustments would help close the gap."})
        elif overall >= 50:
            insights.append({"type": "moderate", "message": "Moderate nutrition adherence -- consistency is the main lever for better results."})
        else:
            insights.append({"type": "needs_improvement", "message": "Nutrition tracking/adherence needs significant improvement."})

        if adherence["protein"] < 80:
            deficit = round(data["goals"]["protein"] - data["averages"]["protein"], 1)
            insights.append({
                "type": "warning", "category": "protein",
                "message": f"Protein intake is below target by about {deficit}g/day.",
            })
        elif adherence["protein"] >= 95:
            insights.append({"type": "success", "category": "protein", "message": "Protein intake is on target, supporting recovery and muscle maintenance."})

        # adherence["calories"] is capped at 100 by design (it also feeds the
        # "overall adherence" score, where an overeating day shouldn't count
        # as *more* than fully met), so it can't detect overeating. The raw,
        # uncapped ratio is computed here and also exported in key_metrics
        # so the combined recommendations can use it.
        goal_calories = data["goals"]["calories"]
        calorie_ratio = round((data["averages"]["calories"] / goal_calories) * 100) if goal_calories else 0

        if adherence["calories"] < 85:
            deficit = round(goal_calories - data["averages"]["calories"], 0)
            insights.append({
                "type": "warning", "category": "calories",
                "message": f"Calorie intake is about {deficit} kcal/day below target.",
            })
        elif calorie_ratio > 110:
            surplus = round(data["averages"]["calories"] - goal_calories, 0)
            insights.append({
                "type": "warning", "category": "calories",
                "message": f"Calorie intake is about {surplus} kcal/day above target.",
            })

        tracking_rate = round((data["total_days_tracked"] / data["period_days"]) * 100, 0) if data["period_days"] else 0
        if tracking_rate < 70:
            insights.append({
                "type": "improvement", "category": "consistency",
                "message": f"Only {data['total_days_tracked']} of {data['period_days']} days tracked ({tracking_rate:.0f}%) -- aim for daily logging.",
            })
        elif tracking_rate >= 90:
            insights.append({"type": "success", "category": "consistency", "message": f"Excellent tracking consistency ({tracking_rate:.0f}%)."})

        return {
            "status": "analyzed",
            "overall_adherence": overall,
            "insights": insights,
            "key_metrics": {
                "protein_adherence": adherence["protein"],
                "calorie_adherence": adherence["calories"],
                "calorie_ratio": calorie_ratio,
                "tracking_consistency": tracking_rate,
            },
        }

    def _analyze_workout(self, data):
        if not data.get("has_data"):
            return {"status": "insufficient_data", "insights": []}

        insights = []
        freq = data["workouts_per_week"]
        avg_duration = data["average_workout_duration"]

        # Every account is a beginner (see the workout generator), so very
        # high frequency is flagged for recovery instead of praised.
        if freq >= 6:
            insights.append({"type": "caution", "category": "recovery", "message": f"Training {freq}/week leaves little time to recover -- make sure you're taking rest days."})
        elif freq >= 4:
            insights.append({"type": "excellent", "message": f"Strong workout frequency ({freq}/week)."})
        elif freq >= 3:
            insights.append({"type": "good", "message": f"Good workout frequency ({freq}/week) -- consistent effort."})
        elif freq >= 2:
            insights.append({"type": "moderate", "message": f"Moderate frequency ({freq}/week) -- aim for 3-4/week for better results."})
        else:
            insights.append({"type": "needs_improvement", "message": f"Low workout frequency ({freq}/week) -- try to build up to at least 2-3/week."})

        if avg_duration < 30:
            insights.append({"type": "warning", "category": "duration", "message": f"Average session is short ({avg_duration} min) -- consider 45-60 min sessions."})
        elif avg_duration > 90:
            insights.append({"type": "caution", "category": "duration", "message": f"Sessions are quite long ({avg_duration} min) -- watch for overtraining and ensure recovery."})
        else:
            insights.append({"type": "success", "category": "duration", "message": f"Session duration ({avg_duration} min) is in a solid range."})

        variety = data.get("exercise_variety", 0)
        if variety < 5:
            insights.append({"type": "improvement", "category": "variety", "message": f"Limited exercise variety ({variety} unique exercises) -- add more for balanced development."})
        elif variety >= 10:
            insights.append({"type": "success", "category": "variety", "message": f"Great exercise variety ({variety} unique exercises)."})

        return {
            "status": "analyzed",
            "insights": insights,
            "key_metrics": {
                "workout_frequency": freq,
                "average_duration": avg_duration,
                "total_workouts": data["total_workouts"],
                "exercise_variety": variety,
            },
        }

    def _analyze_weight(self, data):
        if not data.get("has_data"):
            return {"status": "insufficient_data", "insights": []}

        insights = []
        change = data["change_kg"]
        entries_logged = data["entries_logged"]
        trend_vs_goal = None   # "at_goal" | "toward" | "steady" | "away" | None
        goal_direction = None  # "down" (needs to lose) | "up" (needs to gain) | None

        if entries_logged < 2:
            insights.append({
                "type": "improvement", "category": "consistency",
                "message": "Only one weigh-in logged this period -- log weight regularly (e.g. weekly) to see a real trend, not just a single number.",
            })
        else:
            steady = abs(change) < WEIGHT_NOISE_KG
            if steady:
                insights.append({
                    "type": "info", "category": "trend",
                    "message": "Weight stayed steady over the period (within normal day-to-day variation).",
                })
            else:
                direction = "decreased" if change < 0 else "increased"
                insights.append({
                    "type": "info", "category": "trend",
                    "message": f"Weight {direction} by {abs(change)} kg over the period, averaging {abs(data['weekly_rate_kg'])} kg/week.",
                })

            goal_weight = data.get("goal_weight_kg")
            if goal_weight:
                remaining = round(data["end_weight_kg"] - goal_weight, 1)
                goal_direction = "down" if remaining > 0 else "up"
                if abs(remaining) < 0.5:
                    trend_vs_goal = "at_goal"
                    insights.append({"type": "excellent", "category": "goal", "message": "Right around goal weight."})
                elif steady:
                    trend_vs_goal = "steady"
                    insights.append({
                        "type": "moderate", "category": "goal",
                        "message": f"Weight is steady -- about {abs(remaining)} kg from goal.",
                    })
                elif (remaining > 0 and change < 0) or (remaining < 0 and change > 0):
                    trend_vs_goal = "toward"
                    insights.append({
                        "type": "success", "category": "goal",
                        "message": f"Trending toward goal weight -- about {abs(remaining)} kg to go.",
                    })
                else:
                    trend_vs_goal = "away"
                    insights.append({
                        "type": "caution", "category": "goal",
                        "message": f"Trending away from goal weight -- about {abs(remaining)} kg remaining.",
                    })

        return {
            "status": "analyzed",
            "insights": insights,
            "key_metrics": {
                "change_kg": change,
                "weekly_rate_kg": data["weekly_rate_kg"],
                "entries_logged": entries_logged,
                "trend_vs_goal": trend_vs_goal,
                "goal_direction": goal_direction,
            },
        }

    def _combine_recommendations(self, nutrition_insights, workout_insights, weight_insights=None):
        recs = []
        n_ok = nutrition_insights["status"] == "analyzed"
        w_ok = workout_insights["status"] == "analyzed"
        weight_insights = weight_insights or {"status": "insufficient_data"}
        wt_ok = weight_insights["status"] == "analyzed"

        if n_ok and w_ok:
            nm = nutrition_insights["key_metrics"]
            wm = workout_insights["key_metrics"]

            if wm["workout_frequency"] >= 4 and nm["calorie_adherence"] < 85:
                recs.append({
                    "priority": "high", "category": "nutrition_workout_balance",
                    "recommendation": "Training frequently but under-eating -- increase calorie intake to support recovery.",
                })
            if wm["workout_frequency"] >= 3 and nm["protein_adherence"] < 80:
                recs.append({
                    "priority": "high", "category": "protein_for_recovery",
                    "recommendation": "Increase protein intake to support muscle recovery given current training load.",
                })
            if nutrition_insights["overall_adherence"] >= 80 and wm["workout_frequency"] < 2:
                recs.append({
                    "priority": "medium", "category": "increase_activity",
                    "recommendation": "Nutrition is on track -- increasing workout frequency would compound results.",
                })
            # Fallback for cases that don't match the specific combos above
            # but are still clearly in need of attention on both fronts.
            if nutrition_insights["overall_adherence"] < 50 and wm["workout_frequency"] < 2:
                recs.append({
                    "priority": "high", "category": "foundational_habits",
                    "recommendation": "Both nutrition tracking and workout frequency are low -- start with one small, consistent habit (e.g. logging meals daily) before adding more.",
                })
        elif n_ok and not w_ok:
            recs.append({"priority": "high", "category": "start_training", "recommendation": "Start logging workouts to get frequency/duration feedback."})
        elif w_ok and not n_ok:
            recs.append({"priority": "high", "category": "start_tracking", "recommendation": "Start tracking nutrition to get adherence and macro feedback."})

        # Weight moving away from goal: connect it to what the nutrition
        # data says, instead of leaving two unrelated messages.
        if n_ok and wt_ok:
            wk = weight_insights["key_metrics"]
            nm = nutrition_insights["key_metrics"]
            if wk["trend_vs_goal"] == "away":
                if wk["goal_direction"] == "down" and nm["calorie_ratio"] > 110:
                    recs.append({
                        "priority": "high", "category": "weight_calorie_mismatch",
                        "recommendation": "Weight is rising while calorie intake is above target -- bringing intake back toward your goal is the most direct fix.",
                    })
                elif wk["goal_direction"] == "up" and nm["calorie_adherence"] < 85:
                    recs.append({
                        "priority": "high", "category": "weight_calorie_mismatch",
                        "recommendation": "Weight is dropping while calorie intake is below target -- eating closer to your goal will move you toward your target weight.",
                    })
                else:
                    recs.append({
                        "priority": "medium", "category": "weight_check_logging",
                        "recommendation": "Calories look on target but weight isn't moving toward your goal -- double-check how accurately meals are logged, weigh at the same time of day, and give it a few more weeks.",
                    })

        if n_ok and nutrition_insights["key_metrics"]["tracking_consistency"] < 70:
            recs.append({"priority": "medium", "category": "tracking_consistency", "recommendation": "Log meals daily for more reliable nutrition insights."})

        if not wt_ok and (n_ok or w_ok):
            recs.append({
                "priority": "low", "category": "start_weight_tracking",
                "recommendation": "Log weight weekly to track progress toward your goal alongside nutrition and workouts.",
            })

        # De-duplicate categories in case multiple branches produced an
        # overlapping recommendation, then order by priority (stable, so
        # rules of the same priority keep their original order).
        seen_categories = set()
        deduped = []
        for rec in recs:
            if rec["category"] not in seen_categories:
                deduped.append(rec)
                seen_categories.add(rec["category"])
        deduped.sort(key=lambda r: PRIORITY_ORDER[r["priority"]])
        return deduped