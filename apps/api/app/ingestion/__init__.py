from app.ingestion.eurostat_comext import EurostatComextConnector
from app.ingestion.manual_csv import ManualCsvConnector

#: Connectors that can be triggered by name (API connectors only; manual uploads use their own endpoint).
CONNECTORS = {EurostatComextConnector.name: EurostatComextConnector}

__all__ = ["CONNECTORS", "EurostatComextConnector", "ManualCsvConnector"]
