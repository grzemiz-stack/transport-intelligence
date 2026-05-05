"""Country Supervisor dla Liechtenstein (LI).

Zarzadza agentami zbierajacymi dane z Liechtenstein: policja, media, fora,
telegram, reddit, alerty drogowe, rejestry finansowe.
Laduje konfiguracje z config.yaml, monitoruje zdrowie agentow
i raportuje do Master Supervisora.
"""

from pathlib import Path

from src.agents.base_supervisor import CountrySupervisor

CONFIG_PATH = Path(__file__).parent / "config.yaml"


class LISupervisor(CountrySupervisor):
    """Supervisor agentow dla Liechtenstein."""

    def __init__(self):
        super().__init__(country_code="LI", config_path=CONFIG_PATH)
        self.load_config()
