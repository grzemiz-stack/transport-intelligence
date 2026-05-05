"""Country Supervisor dla Netherlands (NL).

Zarzadza agentami zbierajacymi dane z Netherlands: policja, media, fora,
telegram, reddit, alerty drogowe, rejestry finansowe.
Laduje konfiguracje z config.yaml, monitoruje zdrowie agentow
i raportuje do Master Supervisora.
"""

from pathlib import Path

from src.agents.base_supervisor import CountrySupervisor

CONFIG_PATH = Path(__file__).parent / "config.yaml"


class NLSupervisor(CountrySupervisor):
    """Supervisor agentow dla Netherlands."""

    def __init__(self):
        super().__init__(country_code="NL", config_path=CONFIG_PATH)
        self.load_config()
