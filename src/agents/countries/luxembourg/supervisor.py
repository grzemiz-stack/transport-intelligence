"""Country Supervisor dla Luxembourg (LU).

Zarzadza agentami zbierajacymi dane z Luxembourg: policja, media, fora,
telegram, reddit, alerty drogowe, rejestry finansowe.
Laduje konfiguracje z config.yaml, monitoruje zdrowie agentow
i raportuje do Master Supervisora.
"""

from pathlib import Path

from src.agents.base_supervisor import CountrySupervisor

CONFIG_PATH = Path(__file__).parent / "config.yaml"


class LUSupervisor(CountrySupervisor):
    """Supervisor agentow dla Luxembourg."""

    def __init__(self):
        super().__init__(country_code="LU", config_path=CONFIG_PATH)
        self.load_config()
