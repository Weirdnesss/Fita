from django.contrib import admin

from .models import PerformedExercise, TemplateExercise, TemplateHistory, WgerExercise, WorkoutTemplate

admin.site.register(WorkoutTemplate)
admin.site.register(TemplateExercise)
admin.site.register(TemplateHistory)
admin.site.register(PerformedExercise)
admin.site.register(WgerExercise)
