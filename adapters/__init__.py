"""Registry of source adapters. To add a new portal, import it here and add to ADAPTERS."""
from .base import BaseAdapter
from .remotive import RemotiveAdapter
from .weworkremotely import WeWorkRemotelyAdapter
from .workingnomads import WorkingNomadsAdapter
from .himalayas import HimalayasAdapter
from .jobgether import JobgetherAdapter
from .freelancermap import FreelancermapAdapter
from .dynamitejobs import DynamiteJobsAdapter
from .startupjobs_cz import StartupJobsCzAdapter
from .welcometothejungle import WelcomeToTheJungleAdapter
from .theorg import TheOrgAdapter
from .eustartups import EuStartupsAdapter


ADAPTERS: dict[str, type[BaseAdapter]] = {
    "remotive": RemotiveAdapter,
    "weworkremotely": WeWorkRemotelyAdapter,
    "workingnomads": WorkingNomadsAdapter,
    "himalayas": HimalayasAdapter,
    "jobgether": JobgetherAdapter,
    "freelancermap": FreelancermapAdapter,
    "dynamitejobs": DynamiteJobsAdapter,
    "startupjobs_cz": StartupJobsCzAdapter,
    "welcometothejungle": WelcomeToTheJungleAdapter,
    "theorg": TheOrgAdapter,
    "eustartups": EuStartupsAdapter,
}


def get_adapter(name: str) -> type[BaseAdapter] | None:
    return ADAPTERS.get(name)"""Registry of source adapters. To add a new portal, import it here and add to ADAPTERS."""
from .base import BaseAdapter
from .remotive import RemotiveAdapter
from .weworkremotely import WeWorkRemotelyAdapter
from .workingnomads import WorkingNomadsAdapter
from .himalayas import HimalayasAdapter
from .jobgether import JobgetherAdapter
from .freelancermap import FreelancermapAdapter
from .dynamitejobs import DynamiteJobsAdapter
from .startupjobs_cz import StartupJobsCzAdapter


# Map adapter names (as used in config.yaml) to classes.
ADAPTERS: dict[str, type[BaseAdapter]] = {
    "remotive": RemotiveAdapter,
    "weworkremotely": WeWorkRemotelyAdapter,
    "workingnomads": WorkingNomadsAdapter,
    "himalayas": HimalayasAdapter,
    "jobgether": JobgetherAdapter,
    "freelancermap": FreelancermapAdapter,
    "dynamitejobs": DynamiteJobsAdapter,
    "startupjobs_cz": StartupJobsCzAdapter,
}


def get_adapter(name: str) -> type[BaseAdapter] | None:
    return ADAPTERS.get(name)
