"""Country Supervisor dla Bosnia and Herzegovina (BA).

Zarzadza agentami zbierajacymi dane z Bosnia and Herzegovina: policja, media, fora,
telegram, reddit, alerty drogowe, rejestry finansowe.
Laduje konfiguracje z config.yaml, monitoruje zdrowie agentow
i raportuje do Master Supervisora.
"""

from pathlib import Path

from src.agents.base_supervisor import CountrySupervisor

CONFIG_PATH = Path(__file__).parent / "config.yaml"


class BASupervisor(CountrySupervisor):
    """Supervisor agentow dla Bosnia and Herzegovina."""

    def __init__(self):
        super().__init__(country_code="BA", config_path=CONFIG_PATH)
        self.load_config()
