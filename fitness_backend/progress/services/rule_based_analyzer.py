"""
Applies predefined if-then rules to a user's structured nutrition and
workout data for a period, producing a list of typed insights plus
combined recommendations. This is the "rule-based" half of the hybrid
progress-report approach -- its output feeds into the LLM as grounding
context, so the narrative report stays anchored to real numbers rather
than the model inventing plausible-sounding feedback.
"""


class RuleBasedAnalyzer:
    def analyze_all(self, nutrition_data, workout_data):
        nutrition_insights = self._analyze_nutrition(nutrition_data)
        workout_insights = self._analyze_workout(workout_data)
        return {
            "nutrition_insights": nutrition_insights,
            "workout_insights": workout_insights,
            "overall_recommendations": self._combine_recommendations(
                nutrition_insights, workout_insights
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

        if adherence["calories"] < 85:
            deficit = round(data["goals"]["calories"] - data["averages"]["calories"], 0)
            insights.append({
                "type": "warning", "category": "calories",
                "message": f"Calorie intake is about {deficit} kcal/day below target.",
            })
        elif adherence["calories"] > 110:
            surplus = round(data["averages"]["calories"] - data["goals"]["calories"], 0)
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
                "tracking_consistency": tracking_rate,
            },
        }

    def _analyze_workout(self, data):
        if not data.get("has_data"):
            return {"status": "insufficient_data", "insights": []}

        insights = []
        freq = data["workouts_per_week"]
        avg_duration = data["average_workout_duration"]

        if freq >= 5:
            insights.append({"type": "excellent", "message": f"Outstanding workout frequency ({freq}/week)."})
        elif freq >= 3:
            insights.append({"type": "good", "message": f"Good workout frequency ({freq}/week) -- consistent effort."})
        elif freq >= 2:
            insights.append({"type": "moderate", "message": f"Moderate frequency ({freq}/week) -- aim for 3-5/week for better results."})
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

    def _combine_recommendations(self, nutrition_insights, workout_insights):
        recs = []
        n_ok = nutrition_insights["status"] == "analyzed"
        w_ok = workout_insights["status"] == "analyzed"

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

        if n_ok and nutrition_insights["key_metrics"]["tracking_consistency"] < 70:
            recs.append({"priority": "medium", "category": "tracking_consistency", "recommendation": "Log meals daily for more reliable nutrition insights."})

        # De-duplicate categories in case multiple branches produced an
        # overlapping recommendation (e.g. foundational_habits alongside
        # a more specific one).
        seen_categories = set()
        deduped = []
        for rec in recs:
            if rec["category"] not in seen_categories:
                deduped.append(rec)
                seen_categories.add(rec["category"])
        return deduped
