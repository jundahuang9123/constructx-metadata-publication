"""Bridge to the colleague's ConnectorClient without vendoring the private library."""

from .inventory import InventoryClient, InventorySnapshot


def inventory_from_connector(connector_client, **query_options) -> InventorySnapshot:
    """Use an existing python_connector_lib.ConnectorClient's configuration.

    This only reads assets. It never starts services, onboards, registers assets,
    negotiates contracts, or transfers payload data.
    """
    config = connector_client.config
    return InventoryClient(config.management_api, config.management_key, **query_options).harvest()
