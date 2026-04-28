from __future__ import annotations

import importlib
import inspect


def test_server_mvc_modules_are_importable_directly_from_src_root() -> None:
    config = importlib.import_module("config")
    main = importlib.import_module("main")
    analytics_controller = importlib.import_module("controllers.analytics")
    diagnosis_controller = importlib.import_module("controllers.diagnosis")
    ingestion_controller = importlib.import_module("controllers.ingestion")
    controller_router = importlib.import_module("controllers.router")
    shopify_controller = importlib.import_module("controllers.shopify")
    analytics = importlib.import_module("repositories.analytics")
    diagnosis_repository = importlib.import_module("repositories.diagnosis")
    installation_repository = importlib.import_module("repositories.installations")
    schemas = importlib.import_module("schemas")
    diagnosis_service = importlib.import_module("services.diagnosis")
    ingest_auth = importlib.import_module("services.ingest_auth")
    ingestion_service = importlib.import_module("services.ingestion")
    job_dispatch = importlib.import_module("services.job_dispatch")
    services = importlib.import_module("services.analysis")
    rollups_service = importlib.import_module("services.rollups")
    shop_installations = importlib.import_module("services.shop_installations")
    shopify_service = importlib.import_module("services.shopify")
    worker = importlib.import_module("worker")

    assert config.Settings.__name__ == "Settings"
    assert callable(main.create_app)
    assert analytics_controller.router.__class__.__name__ == "APIRouter"
    assert diagnosis_controller.router.__class__.__name__ == "APIRouter"
    assert ingestion_controller.router.__class__.__name__ == "APIRouter"
    assert controller_router.api_router.__class__.__name__ == "APIRouter"
    assert shopify_controller.router.__class__.__name__ == "APIRouter"
    assert analytics.AnalyticsRepository.__name__ == "AnalyticsRepository"
    assert diagnosis_repository.DiagnosisRepository.__name__ == "DiagnosisRepository"
    assert installation_repository.InstallationRepository.__name__ == "InstallationRepository"
    assert schemas.IngestAcceptedResponse.__name__ == "IngestAcceptedResponse"
    assert schemas.ShopifyOAuthCallbackResponse.__name__ == "ShopifyOAuthCallbackResponse"
    assert schemas.ShopifyWebhookAcceptedResponse.__name__ == "ShopifyWebhookAcceptedResponse"
    assert services.ProductAnalysisService.__name__ == "ProductAnalysisService"
    assert diagnosis_service.ProductDiagnosisService.__name__ == "ProductDiagnosisService"
    assert ingest_auth.IngestAuthService.__name__ == "IngestAuthService"
    assert ingestion_service.EventIngestionService.__name__ == "EventIngestionService"
    assert job_dispatch.JobDispatchService.__name__ == "JobDispatchService"
    assert rollups_service.DailyRollupService.__name__ == "DailyRollupService"
    assert shop_installations.ShopInstallationService.__name__ == "ShopInstallationService"
    assert shopify_service.ShopifyOAuthService.__name__ == "ShopifyOAuthService"
    assert callable(worker.main)


def test_main_module_only_exposes_assembly_helpers() -> None:
    main = importlib.import_module("main")
    main_functions = {
        name
        for name, value in vars(main).items()
        if inspect.isfunction(value) and value.__module__ == "main"
    }

    assert main_functions == {"_ensure_db", "create_app", "run"}
