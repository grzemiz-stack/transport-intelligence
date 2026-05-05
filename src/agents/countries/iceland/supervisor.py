"""Country Supervisor dla Iceland (IS).

Zarzadza agentami zbierajacymi dane z Iceland: policja, media, fora,
telegram, reddit, alerty drogowe, rejestry finansowe.
Laduje konfiguracje z config.yaml, monitoruje zdrowie agentow
i raportuje do Master Supervisora.
"""

from pathlib import Path

from src.agents.base_supervisor import CountrySupervisor

CONFIG_PATH = Path(__file__).parent / "config.yaml"


class ISSupervisor(CountrySupervisor):
    """Supervisor agentow dla Iceland."""

    def __init__(self):
        super().__init__(country_code="IS", config_path=CONFIG_PATH)
        self.load_config()
