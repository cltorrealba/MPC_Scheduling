# Lightweight wrapper to allow legacy absolute import `from model_serializer import StoreSpec, from_json, to_json`
# Delegates to the implementation inside biorefinery_models if available.
from biorefinery_models.model_serializer import StoreSpec, from_json, to_json  # type: ignore
