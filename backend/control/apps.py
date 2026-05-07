from django.apps import AppConfig


class ControlConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'control'

    def ready(self):
        from .services.metric_sampler import start_system_metric_sampler

        start_system_metric_sampler(interval_seconds=30.0)
