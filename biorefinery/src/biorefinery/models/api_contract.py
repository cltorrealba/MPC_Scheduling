from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Dict, Optional, List, Any
import pyomo.environ as pe
from .fermentation import build_fermentation_model
import hashlib, json

@dataclass
class FermentationConfig:
    # Time related (physical horizon expressed in hours for external clarity)
    horizon_h: float = 12.0
    nfe: int = 5
    total_elements_reference: int = 50  # scaling vs full batch (legacy compatibility)
    start_time_s: float = 0.0
    include_kinetics: bool = True
    detailed_kinetics: bool = False
    enable_mass_balance: bool = True
    include_dilution: bool = False
    feed_control: bool = False
    initial_concentrations: Dict[str, float] = field(default_factory=lambda: {
        'G':10.0,'X':5.0,'Eth':0.0,'Cell':1.0,'F':0.2,'HMF':0.1,'ACT':0.05,'CO2':0.0
    })
    initial_hold_up: float = 1000.0
    feed_concentrations: Optional[Dict[str,float]] = None
    # Future placeholders
    scenario_name: Optional[str] = None
    tag: Optional[str] = None

    def to_hash_payload(self) -> Dict[str, Any]:
        keys = ['horizon_h','nfe','total_elements_reference','include_kinetics','detailed_kinetics',
                'enable_mass_balance','include_dilution','feed_control','initial_concentrations','initial_hold_up']
        return {k: getattr(self, k) for k in keys}

@dataclass
class FermentationBuildResult:
    model: pe.ConcreteModel
    config: FermentationConfig
    physical_horizon_s: float
    kinetic_species: List[str]
    product_reactions: List[str]
    species: List[str]
    param_hash: Optional[str]

    def snapshot_state(self) -> Dict[str, Any]:
        m = self.model
        last = m.t.last()
        state = {sp: float(pe.value(m.C[last, sp])) for sp in self.species if (last, sp) in m.C}
        hold_up = float(pe.value(m.M[last])) if hasattr(m, 'M') else None
        return {'C': state, 'M': hold_up}


def compute_kinetics_param_hash(m: pe.ConcreteModel) -> Optional[str]:
    if not hasattr(m, 'component_objects'):
        return None
    params = []
    try:
        for comp in m.component_objects(pe.Param, descend_into=True):
            nm = comp.getname(fully_qualified=True)
            # Filter to kinetic-related
            if any(tok in nm.lower() for tok in ['qmax','y_','k0','k1','k2','ki','kip','ksp','gamma','m_']):
                if comp.is_indexed():
                    for idx in comp:
                        params.append((f"{nm}[{idx}]", float(pe.value(comp[idx]))))
                else:
                    params.append((nm, float(pe.value(comp))))
        params.sort(key=lambda x: x[0])
        raw = json.dumps(params).encode('utf-8')
        return hashlib.sha256(raw).hexdigest()[:16]
    except Exception:
        return None


def build_fermentation_model_v2(cfg: FermentationConfig) -> FermentationBuildResult:
    # Map horizon hours to scaling used by legacy-like builder: horizon fraction over full batch
    physical_horizon_s = cfg.horizon_h * 3600.0
    # We emulate legacy scaling: final_time = (nfe * total_sim_time)/total_elements_reference
    # Solve for total_sim_time so that prediction horizon == physical_horizon_s
    total_sim_time = physical_horizon_s * cfg.total_elements_reference / cfg.nfe
    m = build_fermentation_model(
        n_f_elements_t=cfg.nfe,
        total_f_elements_t=cfg.total_elements_reference,
        total_sim_time=total_sim_time,
        current_start_time_seconds=cfg.start_time_s,
        include_kinetics=cfg.include_kinetics,
        detailed_kinetics=cfg.detailed_kinetics,
        initial_concentrations=cfg.initial_concentrations,
        include_dilution=cfg.include_dilution,
        feed_concentrations=cfg.feed_concentrations,
        enable_mass_balance=cfg.enable_mass_balance,
        feed_control=cfg.feed_control,
    )
    if hasattr(m, 'M0'):
        m.M0.set_value(cfg.initial_hold_up)
    param_hash = compute_kinetics_param_hash(m) if cfg.include_kinetics else None
    kinetic_species = list(m.kinetic_species) if hasattr(m, 'kinetic_species') else []
    product_reactions = list(m.product_reactions) if hasattr(m, 'product_reactions') else []
    species = list(m.j) if hasattr(m, 'j') else []
    return FermentationBuildResult(
        model=m,
        config=cfg,
        physical_horizon_s=physical_horizon_s,
        kinetic_species=kinetic_species,
        product_reactions=product_reactions,
        species=species,
        param_hash=param_hash,
    )

__all__ = [
    'FermentationConfig',
    'FermentationBuildResult',
    'build_fermentation_model_v2',
    'compute_kinetics_param_hash'
]
