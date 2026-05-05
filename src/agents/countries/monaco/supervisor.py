"""Country Supervisor dla Monaco (MC).

Zarzadza agentami zbierajacymi dane z Monaco: policja, media, fora,
telegram, reddit, alerty drogowe, rejestry finansowe.
Laduje konfiguracje z config.yaml, monitoruje zdrowie agentow
i raportuje do Master Supervisora.
"""

from pathlib import Path

from src.agents.base_supervisor import CountrySupervisor

CONFIG_PATH = Path(__file__).parent / "config.yaml"


class MCSupervisor(CountrySupervisor):
    """Supervisor agentow dla Monaco."""

    def __init__(self):
        super().__init__(country_code="MC", config_path=CONFIG_PATH)
        self.load_config()
