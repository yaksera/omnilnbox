from django.contrib import admin

from .models import AIUsage, AssistantSettings, KnowledgeItem, Rule

admin.site.register(AssistantSettings)
admin.site.register(KnowledgeItem)
admin.site.register(Rule)


@admin.register(AIUsage)
class AIUsageAdmin(admin.ModelAdmin):
    list_display = ("workspace", "month", "credits", "tokens")
