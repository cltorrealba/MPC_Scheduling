"""Fermentation model builder (extracted skeleton).

This provides an incremental extraction point from the legacy
`Fermentation_Scheduling_and_MPC.py`. Only a subset of variables/params
is instantiated here so tests and future refactors can target a stable
API. Gradually migrate additional kinetic parameters, constraints, and
DAE structure from the legacy file into this function.

Route deactivation & exact zeros:
---------------------------------
Uptake route on/off decisions enter through the mutable Param ``route_config``.
To avoid tiny denormal residual rates (e.g. -1e-40) when a route is disabled,
we both (a) multiply detailed kinetic expressions by ``route_config[route]`` and
additionally (b) explicitly fix the corresponding uptake variable ``q[t,route]``
to 0.0 when deactivated (see ``set_route_activation``). This guarantees strict
zero values and keeps equality constraints numerically clean for tests & DSDA
comparisons without relying on big-M style upper bounds.
"""
from __future__ import annotations

import pyomo.environ as pe
import pyomo.dae as dae
from typing import Dict, Any, Optional


def build_fermentation_model(
    n_f_elements_t: int = 1,
    total_f_elements_t: int = 50,
    total_sim_time: float = 190 * 60 * 60,
    current_start_time_seconds: float = 0.0,
    keep_constant_flows: bool = False,
    include_kinetics: bool = False,
    detailed_kinetics: bool = False,
    initial_concentrations: Optional[Dict[str, float]] = None,
    include_dilution: bool = False,
    feed_concentrations: Optional[Dict[str, float]] = None,
) -> pe.ConcreteModel:
    """Create a minimal fermentation Pyomo model with optional kinetics and initial conditions.

    Parameters
    ----------
    n_f_elements_t : int
        Number of finite elements in the (current) prediction horizon.
    total_f_elements_t : int
        Total finite elements representing the full batch duration.
    total_sim_time : float
        Total simulation time (s) for the whole batch window.
    current_start_time_seconds : float
        Current horizon absolute start time (s).
    keep_constant_flows : bool
        Placeholder flag (reserved for future feed policy logic).
    include_kinetics : bool
        If True, attaches kinetic parameters, variables, and coarse rate constraints.
    detailed_kinetics : bool
        If True, adds detailed nonlinear uptake expressions (requires include_kinetics=True).
    initial_concentrations : Dict[str, float], optional
        Mapping species -> initial concentration; fixed at first collocation point.
    include_dilution : bool
        If True, adds dilution/feed source terms to concentration balances.
    feed_concentrations : Dict[str,float], optional
        Mapping species -> concentration in feed streams (assumed identical for all feeds);
        defaults to 0 for unspecified species when include_dilution=True.

    Returns
    -------
    ConcreteModel
        Configured fermentation model instance.
    """
    m = pe.ConcreteModel(name="fermentation_skeleton")

    if detailed_kinetics and not include_kinetics:
        raise ValueError("detailed_kinetics=True requires include_kinetics=True")

    # Time horizon metadata
    m.final_time = pe.Param(
        initialize=(n_f_elements_t * total_sim_time) / total_f_elements_t,
        doc="Prediction horizon span [s]",
    )
    m.current_starting_time = pe.Param(
        initialize=current_start_time_seconds, doc="Current start time [s]"
    )
    m.current_final_time = pe.Param(
        initialize=m.current_starting_time + m.final_time, doc="Current final time [s]"
    )

    # Sets
    m.t = dae.ContinuousSet(bounds=(0, 1))
    m.j = pe.Set(
        initialize=[
            "CS",
            "XS",
            "LS",
            "C",
            "G",
            "X",
            "F",
            "E",
            "AC",
            "Cell",
            "Eth",
            "CO2",
            "ACT",
            "HMF",
            "Base",
        ]
    )
    m.e = pe.Set(initialize=["1", "2", "3"])

    # Key parameters (subset)
    m.Mmax = pe.Param(initialize=220000, doc="Maximum hold up [kg]")

    # ------------------------------------------------------------------
    # Optional kinetics parameter subset (uptake / yield constants)
    # Extracted from legacy Fermentation_Scheduling_and_MPC.py. Only
    # parameters, no kinetics variables or constraints yet. These are
    # conditionally attached to keep the default light-weight builder.
    # ------------------------------------------------------------------
    if include_kinetics:
        # Route toggles (1 active, 0 inactive); can be modified externally (mutable Param)
        m.route_config = pe.Param(
            ['G','X','F','HMF','ACT'], initialize=1, mutable=True,
            doc="Activation (1) / deactivation (0) of uptake routes for DSDA"
        )
        # Small epsilon to regularize power expressions and divisions
        m.eps_power = pe.Param(initialize=1e-8, doc="Epsilon to avoid singular derivatives at zero in power terms")
        # Yields & inhibition / saturation parameters (initial migration slice)
        m.Y_CO2_G = pe.Param(initialize=0.47, doc="CO2 production from glucose uptake [kg/kg]")
        m.Y_CO2_X = pe.Param(initialize=0.4, doc="CO2 production from xylose uptake [kg/kg]")
        m.KI_F_S = pe.Param(initialize=0.05, doc="Furfural uptake self inhibition constant [g/kg]")
        m.KI_F_G = pe.Param(initialize=0.75, doc="Glucose inhibition on furfural uptake [g/kg]")
        m.KI_HMF_F = pe.Param(initialize=0.25, doc="Furfural inhibition on 5-HMF uptake [g/kg]")
        m.KI_F_X = pe.Param(initialize=0.35, doc="Xylose inhibition on furfural uptake [g/kg]")
        m.qmax_F = pe.Param(initialize=4.6706e-5, doc="Maximum furfural uptake [1/s]")
        m.KIP_G = pe.Param(initialize=4890, doc="Glucose uptake self inhibition parameter [g/kg]")
        m.KSP_G = pe.Param(initialize=1.342, doc="Glucose uptake self inhibition parameter [g/kg]")
        m.PMP_G = pe.Param(initialize=103, doc="Ethanol inhibition in glucose uptake [g/kg]")
        m.gamma_G = pe.Param(initialize=1.42, doc="Ethanol inhibition in glucose uptake [-]")
        m.Y_Eth_G = pe.Param(initialize=0.47, doc="Ethanol production from glucose uptake [kg/kg]")
        m.Y_Cell_G = pe.Param(initialize=0.115, doc="Biomass growth on glucose [kg/kg]")
        m.m_G = pe.Param(initialize=2.6944e-5, doc="Maintenance coefficient for biomass growth on glucose [1/s]")
        m.qmax_G = pe.Param(initialize=0.000318, doc="Maximum glucose uptake rate [1/s]")
        m.KIP_X = pe.Param(initialize=81.3, doc="Xylose uptake self inhibition parameter [g/kg]")
        m.KSP_X = pe.Param(initialize=3.4, doc="Xylose uptake self inhibition parameter [g/kg]")
        m.PMP_X = pe.Param(initialize=100.2, doc="Ethanol inhibition on xylose uptake [g/kg]")
        m.gamma_X = pe.Param(initialize=0.608, doc="Ethanol inhibition on xylose uptake [-]")
        m.Y_Eth_X = pe.Param(initialize=0.4, doc="Ethanol production from xylose uptake [kg/kg]")
        m.Y_Cell_X = pe.Param(initialize=0.162, doc="Biomass growth on xylose [kg/kg]")
        m.m_X = pe.Param(initialize=1.8611e-5, doc="Maintenance coefficient for biomass growth on xylose [1/s]")
        m.qmax_X = pe.Param(initialize=0.00083444, doc="Maximum xylose uptake rate [1/s]")
        m.KIP_ACT = pe.Param(initialize=2.5, doc="Acetate uptake self inhibition [g/kg]")
        m.KI_ACT_G = pe.Param(initialize=2.74, doc="Acetate inhibition on glucose uptake [g/kg]")
        m.KI_ACT_X = pe.Param(initialize=0.2, doc="Acetate inhibition on xylose uptake [g/kg]")
        m.Y_ACT_HMF = pe.Param(initialize=0.23392, doc="Acetate production from 5HMF uptake [kg/kg]")
        m.Y_CO2_HMF = pe.Param(initialize=0.1, doc="CO2 production from 5HMF uptake [kg/kg]")
        m.qmax_ATC = pe.Param(initialize=1.2292e-5, doc="Maximum acetate uptake rate [1/s]")
        m.KIP_HMF = pe.Param(initialize=0.5, doc="5HMF uptake self inhibition [g/kg]")
        m.KI_HMF_G = pe.Param(initialize=2, doc="5HMF inhibition on glucose uptake [g/kg]")
        m.KI_HMF_X = pe.Param(initialize=10, doc="5HMF inhibition on xylose uptake [g/kg]")
        m.qmax_HMF = pe.Param(initialize=8.7576e-5, doc="Maximum 5HMF uptake rate [1/s]")
        # pH dependency parameters (kept minimal; full usage will come with kinetics constraints)
        m.K0G = pe.Param(initialize=1, doc="pH dependency param (G) K0")
        m.K1G = pe.Param(initialize=5.388758642823563, doc="pH dependency param (G) K1")
        m.K2G = pe.Param(initialize=0.009698396119741, doc="pH dependency param (G) K2")
        m.K0X = pe.Param(initialize=1, doc="pH dependency param (X) K0")
        m.K1X = pe.Param(initialize=5.375237819425663, doc="pH dependency param (X) K1")
        m.K2X = pe.Param(initialize=0.009314982725521, doc="pH dependency param (X) K2")

    # Feed related variables
    m.F_C5liquid = pe.Var(
        m.t,
        initialize=628 * (1 / 60) * (1 / 60),
        within=pe.NonNegativeReals,
        bounds=(0, 2 * 628 * (1 / 60) * (1 / 60)),
    )
    m.F_liquified_fibers = pe.Var(
        m.t,
        initialize=2487 * (1 / 60) * (1 / 60),
        within=pe.NonNegativeReals,
        bounds=(0, 2 * 2487 * (1 / 60) * (1 / 60)),
    )

    # Simplified species concentrations (initially zero; real init handled externally)
    m.C = pe.Var(m.t, m.j, initialize=0, within=pe.NonNegativeReals, bounds=(0, 1000))
    m.M = pe.Var(m.t, initialize=1, within=pe.NonNegativeReals, bounds=(0, m.Mmax))

    # Apply initial concentrations if provided
    if initial_concentrations:
        first_t = m.t.first()
        for sp, val in initial_concentrations.items():
            if sp in m.j:
                m.C[first_t, sp].fix(val)
            else:
                raise ValueError(f"Initial concentration provided for unknown species {sp}")

    # pH (single variable vs time-indexed for now)
    m.pH = pe.Var(initialize=5.39, bounds=(5.0, 6.0))

    # Derivatives (skeleton only, not linked yet)
    m.dCdt = dae.DerivativeVar(m.C, wrt=m.t)
    m.dMdt = dae.DerivativeVar(m.M, wrt=m.t)

    # Kinetics variables (uptake/production rates) guarded by flag
    if include_kinetics:
        # Uptake / conversion rates for key substrates & products
        # We keep the index subset explicit to avoid pulling every species prematurely.
        kinetic_species = ["G", "X", "F", "HMF", "ACT"]  # substrates whose uptake is modeled
        product_reactions = ["Eth", "ACT_from_HMF", "CO2_total"]  # aggregated reaction rate pools
        m.kinetic_species = pe.Set(initialize=kinetic_species)
        m.product_reactions = pe.Set(initialize=product_reactions)

        # q[t,s] substrate uptake (positive defined here as substrate consumption rate)
        m.q = pe.Var(m.t, m.kinetic_species, within=pe.NonNegativeReals)
        # R[t,r] product/aggregate reaction formation rates
        m.R = pe.Var(m.t, m.product_reactions, within=pe.NonNegativeReals)

    # Basic feed mass balance skeleton
    def _Diff_mass(m, t):
        if t == m.t.first() and m.current_starting_time == 0:
            return m.M[t] == 1.0  # placeholder initial M0
        elif t == m.t.first():
            return pe.Constraint.Skip  # would link previous batch state
        else:
            return m.dMdt[t] == m.final_time * (m.F_C5liquid[t] + m.F_liquified_fibers[t])

    m.Diff_mass = pe.Constraint(m.t, rule=_Diff_mass)

    # Phase-wise feed logic (reduced form)
    def _phase_feed_assign(m, t):
        abs_t = m.current_starting_time + t * (m.current_final_time - m.current_starting_time)
        if abs_t <= 10 * 60 * 60:
            return pe.Constraint.Skip  # initial inoculum phase (defaults stand)
        elif abs_t <= 70 * 60 * 60:
            return pe.Constraint.Skip
        else:
            # batch phase: flows zeroed
            return m.F_C5liquid[t] + m.F_liquified_fibers[t] == 0

    m.phase_feed_assign = pe.Constraint(m.t, rule=_phase_feed_assign)

    # ------------------------------------------------------------------
    # Stub kinetics constraints (very coarse). These provide structural
    # linking between substrate uptake and product formation to enable
    # early testing. Detailed nonlinear inhibition & pH kinetics will
    # be migrated later (kept as commented templates referencing the
    # legacy script). Assumptions: instantaneous yield relationships.
    # ------------------------------------------------------------------
    if include_kinetics:
        def _ethanol_rate(m, t):
            # Ethanol formation from glucose & xylose uptake
            return m.R[t, "Eth"] == m.q[t, "G"] * m.Y_Eth_G + m.q[t, "X"] * m.Y_Eth_X

        m.ethanol_rate = pe.Constraint(m.t, rule=_ethanol_rate)

        def _acetate_from_hmf(m, t):
            # Simplified: acetate from HMF uptake (no acetate consumption yet)
            return m.R[t, "ACT_from_HMF"] == m.q[t, "HMF"] * m.Y_ACT_HMF

        m.acetate_from_hmf_rate = pe.Constraint(m.t, rule=_acetate_from_hmf)

        def _co2_total(m, t):
            # CO2 from glucose, xylose and HMF (placeholder aggregate)
            return (
                m.R[t, "CO2_total"]
                == m.q[t, "G"] * m.Y_CO2_G
                + m.q[t, "X"] * m.Y_CO2_X
                + m.q[t, "HMF"] * m.Y_CO2_HMF
            )

        m.co2_rate = pe.Constraint(m.t, rule=_co2_total)

        # -----------------Future detailed kinetics templates-----------------
        # Below are illustrative commented expressions ported from legacy code
        # (Gaussian pH dependence & inhibition factors). They will be added
        # gradually with appropriate indexing and activation logic.
        #
        # Example (glucose uptake detailed form):
        # q_G = (1/m.Y_Eth_G) * (
        #     (m.qmax_G * (m.K0G * pe.exp(-(((m.pH - m.K1G)**2)/(2*(m.K2G**2))))))
        #     * m.C[t,'Cell'] * ( m.C[t,'G'] / (m.KSP_G + m.C[t,'G'] + (m.C[t,'G']**2)/m.KIP_G) )
        # ) * (1 - (m.C[t,'Eth']/m.PMP_G)**m.gamma_G) 
        #   * (m.KI_F_G / (m.KI_F_G + m.C[t,'F']))
        #   * (m.KI_ACT_G / (m.KI_ACT_G + m.C[t,'ACT']))
        #   * (m.KI_HMF_G / (m.KI_HMF_G + m.C[t,'HMF']))
        #
        # Similar pattern for xylose (q_X) and other inhibitors.
        # ------------------------------------------------------------------
        if detailed_kinetics:
            # Detailed kinetic expressions for glucose & xylose uptake
            # Positive uptake rate q[G], q[X] already represent substrate consumption
            def _q_glucose(m, t):
                if t == m.t.first():
                    return pe.Constraint.Skip  # rely on initialization for first point
                # Gaussian pH factor
                pH_term = m.K0G * pe.exp(-(((m.pH - m.K1G) ** 2) / (2 * (m.K2G ** 2))))
                sat = m.C[t, 'G'] / (m.KSP_G + m.C[t, 'G'] + (m.C[t, 'G'] ** 2) / m.KIP_G)
                # Smooth ethanol inhibition avoiding pow'(0, gamma) issue:
                # 1 - ((Eth + eps)/PMP)^gamma  -> rewrite via exp(gamma * log((Eth+eps)/PMP))
                eth_ratio_G = (m.C[t, 'Eth'] + m.eps_power) / m.PMP_G
                inhib_eth = 1 - pe.exp(m.gamma_G * pe.log(eth_ratio_G))
                inhib_F = m.KI_F_G / (m.KI_F_G + m.C[t, 'F'])
                inhib_ACT = m.KI_ACT_G / (m.KI_ACT_G + m.C[t, 'ACT'])
                inhib_HMF = m.KI_HMF_G / (m.KI_HMF_G + m.C[t, 'HMF'])
                expr_active = (1 / m.Y_Eth_G) * (m.qmax_G * pH_term * m.C[t, 'Cell'] * sat) * inhib_eth * inhib_F * inhib_ACT * inhib_HMF
                # Equality drives q to zero automatically if route_config['G']==0
                return m.q[t, 'G'] == m.route_config['G'] * expr_active

            m.q_glucose_rate = pe.Constraint(m.t, rule=_q_glucose)

            def _q_xylose(m, t):
                if t == m.t.first():
                    return pe.Constraint.Skip
                pH_term = m.K0X * pe.exp(-(((m.pH - m.K1X) ** 2) / (2 * (m.K2X ** 2))))
                sat = m.C[t, 'X'] / (m.KSP_X + m.C[t, 'X'] + (m.C[t, 'X'] ** 2) / m.KIP_X)
                eth_ratio_X = (m.C[t, 'Eth'] + m.eps_power) / m.PMP_X
                inhib_eth = 1 - pe.exp(m.gamma_X * pe.log(eth_ratio_X))
                inhib_F = m.KI_F_X / (m.KI_F_X + m.C[t, 'F'])
                inhib_ACT = m.KI_ACT_X / (m.KI_ACT_X + m.C[t, 'ACT'])
                inhib_HMF = m.KI_HMF_X / (m.KI_HMF_X + m.C[t, 'HMF'])
                expr_active = (1 / m.Y_Eth_X) * (m.qmax_X * pH_term * m.C[t, 'Cell'] * sat) * inhib_eth * inhib_F * inhib_ACT * inhib_HMF
                return m.q[t, 'X'] == m.route_config['X'] * expr_active

            m.q_xylose_rate = pe.Constraint(m.t, rule=_q_xylose)

            # Furfural uptake (analogous pattern): self-inhibition + cross inhibitions (using available params)
            def _q_furfural(m, t):
                if t == m.t.first():
                    return pe.Constraint.Skip
                # Saturation / self & cross inhibition structure (simplified placeholder)
                # Reusing KI params: KI_F_G (glucose inhibiting F), KI_F_X (xylose inhibiting F), KI_F_S (self)
                sat_self = m.C[t, 'F'] / (m.KI_F_S + m.C[t, 'F'])
                inhib_G = m.KI_F_G / (m.KI_F_G + m.C[t, 'G'])
                inhib_X = m.KI_F_X / (m.KI_F_X + m.C[t, 'X'])
                expr_active = m.qmax_F * m.C[t, 'Cell'] * sat_self * inhib_G * inhib_X
                return m.q[t, 'F'] == m.route_config['F'] * expr_active

            m.q_furfural_rate = pe.Constraint(m.t, rule=_q_furfural)

            # 5-HMF uptake with inhibition by furfural and self inhibition (placeholders based on parameters present)
            def _q_hmf(m, t):
                if t == m.t.first():
                    return pe.Constraint.Skip
                self_term = m.C[t, 'HMF'] / (m.KIP_HMF + m.C[t, 'HMF'])
                inhib_F = m.KI_HMF_G / (m.KI_HMF_G + m.C[t, 'F'])  # reuse KI_HMF_G as generic cross factor
                expr_active = m.qmax_HMF * m.C[t, 'Cell'] * self_term * inhib_F
                return m.q[t, 'HMF'] == m.route_config['HMF'] * expr_active

            m.q_hmf_rate = pe.Constraint(m.t, rule=_q_hmf)

            # Acetate uptake with self inhibition (KIP_ACT). Additional inhibitions could be added later.
            def _q_acetate(m, t):
                if t == m.t.first():
                    return pe.Constraint.Skip
                self_term = m.C[t, 'ACT'] / (m.KIP_ACT + m.C[t, 'ACT'])
                expr_active = m.qmax_ATC * m.C[t, 'Cell'] * self_term
                return m.q[t, 'ACT'] == m.route_config['ACT'] * expr_active

            m.q_acetate_rate = pe.Constraint(m.t, rule=_q_acetate)

            # (Big-M upper bounds removed; exact zeros enforced by fixing q when route disabled.)

        # If NOT using detailed kinetics, add simplified saturation equalities
        if not detailed_kinetics:
            def _qG_simple(m, t):
                if t == m.t.first():
                    return pe.Constraint.Skip
                sat = m.C[t, 'G'] / (m.KSP_G + m.C[t, 'G'] + (m.C[t, 'G'] ** 2) / m.KIP_G)
                expr = m.qmax_G * m.C[t, 'Cell'] * sat
                return m.q[t, 'G'] == m.route_config['G'] * expr
            m.qG_simple = pe.Constraint(m.t, rule=_qG_simple)

            def _qX_simple(m, t):
                if t == m.t.first():
                    return pe.Constraint.Skip
                sat = m.C[t, 'X'] / (m.KSP_X + m.C[t, 'X'] + (m.C[t, 'X'] ** 2) / m.KIP_X)
                expr = m.qmax_X * m.C[t, 'Cell'] * sat
                return m.q[t, 'X'] == m.route_config['X'] * expr
            m.qX_simple = pe.Constraint(m.t, rule=_qX_simple)

            def _qF_simple(m, t):
                if t == m.t.first():
                    return pe.Constraint.Skip
                sat = m.C[t, 'F'] / (m.KI_F_S + m.C[t, 'F'])
                expr = m.qmax_F * m.C[t, 'Cell'] * sat
                return m.q[t, 'F'] == m.route_config['F'] * expr
            m.qF_simple = pe.Constraint(m.t, rule=_qF_simple)

            def _qHMF_simple(m, t):
                if t == m.t.first():
                    return pe.Constraint.Skip
                sat = m.C[t, 'HMF'] / (m.KIP_HMF + m.C[t, 'HMF'])
                expr = m.qmax_HMF * m.C[t, 'Cell'] * sat
                return m.q[t, 'HMF'] == m.route_config['HMF'] * expr
            m.qHMF_simple = pe.Constraint(m.t, rule=_qHMF_simple)

            def _qACT_simple(m, t):
                if t == m.t.first():
                    return pe.Constraint.Skip
                sat = m.C[t, 'ACT'] / (m.KIP_ACT + m.C[t, 'ACT'])
                expr = m.qmax_ATC * m.C[t, 'Cell'] * sat
                return m.q[t, 'ACT'] == m.route_config['ACT'] * expr
            m.qACT_simple = pe.Constraint(m.t, rule=_qACT_simple)

        # ------------------------------------------------------------------
        # Concentration balances (initial subset) for substrates & ethanol
        # dC/dt (dimensionless time) * final_time = physical rate. We link
        # consumption/production ignoring dilution & feed terms for now.
        # Signs: q (uptake) consumes substrate; R['Eth'] produces ethanol.
        # TODO: integrate feed dilution and cell growth coupling.
        # ------------------------------------------------------------------
        tracked_balances = ['G', 'X', 'Eth', 'F', 'HMF', 'ACT', 'Cell', 'CO2']

        # Precompute total flow and feed concentrations (only if dilution enabled)
        if include_dilution:
            # Parameter for feed concentrations (species not provided -> 0)
            def _feed_conc_init(j):
                if feed_concentrations and j in feed_concentrations:
                    return feed_concentrations[j]
                return 0.0
            m.feed_conc = pe.Param(m.j, initialize=_feed_conc_init, mutable=True, doc="Feed concentrations [g/kg or consistent units]")

            def _total_flow(m, t):
                return m.F_C5liquid[t] + m.F_liquified_fibers[t]
            m.total_flow = pe.Expression(m.t, rule=_total_flow)

            # Effective dilution coefficient D = F_total / M (avoid division by zero; M bounded >0)
            def _dilution(m, t):
                return m.total_flow[t] / pe.maximize(1e-6, m.M[t])  # safeguard tiny mass
            # Pyomo lacks direct maximize in expressions; fallback: small epsilon logic below
            # We'll implement safe division manually in each balance rather than expression.
        # Small epsilon to avoid division by zero in dilution terms
        m.eps_div = pe.Param(initialize=1e-6, doc="Small epsilon for safe division in dilution")

        def _balance_rule(comp):
            def _rule(b, t):
                M = b.model()  # parent model
                if t == M.t.first():
                    return pe.Constraint.Skip  # handled via initial condition mechanism
                # Common helper for dilution source/sink
                def _with_dilution(core_rhs):
                    if not include_dilution:
                        return core_rhs
                    total_flow = M.F_C5liquid[t] + M.F_liquified_fibers[t]
                    denom = M.M[t] + M.eps_div
                    return core_rhs - total_flow * M.C[t, comp] / denom + total_flow * M.feed_conc[comp] / denom
                if comp == 'G':
                    return M.dCdt[t, 'G'] * M.final_time == _with_dilution(-M.q[t, 'G'])
                if comp == 'X':
                    return M.dCdt[t, 'X'] * M.final_time == _with_dilution(-M.q[t, 'X'])
                if comp == 'Eth':
                    return M.dCdt[t, 'Eth'] * M.final_time == _with_dilution(M.R[t, 'Eth'])
                if comp == 'F':
                    return M.dCdt[t, 'F'] * M.final_time == _with_dilution(-M.q[t, 'F'])
                if comp == 'HMF':
                    return M.dCdt[t, 'HMF'] * M.final_time == _with_dilution(-M.q[t, 'HMF'])
                if comp == 'ACT':
                    return M.dCdt[t, 'ACT'] * M.final_time == _with_dilution(M.q[t, 'HMF'] * M.Y_ACT_HMF - M.q[t, 'ACT'])
                if comp == 'Cell':
                    core = (M.q[t, 'G'] * M.Y_Cell_G + M.q[t, 'X'] * M.Y_Cell_X - (M.m_G + M.m_X) * M.C[t, 'Cell'])
                    return M.dCdt[t, 'Cell'] * M.final_time == _with_dilution(core)
                if comp == 'CO2':
                    return M.dCdt[t, 'CO2'] * M.final_time == _with_dilution(M.R[t, 'CO2_total'])
                return pe.Constraint.Skip
            return _rule

        m.concentration_balances = pe.Block()
        for comp in tracked_balances:
            setattr(
                m.concentration_balances,
                f"bal_{comp}",
                pe.Constraint(m.t, rule=_balance_rule(comp))
            )

    # Discretize in time (collocation skeleton)
    discretizer_t = pe.TransformationFactory("dae.collocation")
    discretizer_t.apply_to(m, nfe=n_f_elements_t, ncp=1, wrt=m.t)

    # Objective placeholder (e.g., maximize ethanol concentration final point)
    ethanol = "Eth"

    def _obj(m):
        return -m.C[m.t.last(), ethanol]  # maximize Eth via minimization

    m.obj = pe.Objective(rule=_obj)

    return m

def set_route_activation(model, route_name: str, active: bool):
    """Toggle a kinetic uptake route on/off (intended for DSDA neighborhood moves).

    Parameters
    ----------
    model : ConcreteModel
        Model returned by build_fermentation_model(include_kinetics=True).
    route_name : str
        One of 'G','X','F','HMF','ACT'.
    active : bool
        True activates route (1), False deactivates (0).
    """
    if not hasattr(model, 'route_config'):
        raise AttributeError("Model has no route_config; build with include_kinetics=True")
    if route_name not in model.route_config:
        raise ValueError(f"Unknown route {route_name}")
    model.route_config[route_name] = 1 if active else 0
    # If kinetics variables exist, fix/unfix q for strict zero semantics
    if hasattr(model, 'q') and route_name in model.kinetic_species:
        for t in model.t:
            var = model.q[t, route_name]
            if active:
                if var.fixed:
                    var.unfix()
            else:
                # Fix to zero regardless of prior value
                if abs(var.value or 0.0) > 1e-14:
                    var.set_value(0.0)
                var.fix(0.0)
    # If kinetics defined, fix/unfix associated uptake variable(s) for exact zeros
    if hasattr(model, 'q') and route_name in model.kinetic_species:
        if not active:
            for t in model.t:
                if (t, route_name) in model.q:
                    model.q[t, route_name].set_value(0.0)
                    model.q[t, route_name].fix(0.0)
        else:
            for t in model.t:
                if (t, route_name) in model.q and model.q[t, route_name].fixed:
                    model.q[t, route_name].unfix()

__all__ = ["build_fermentation_model", "set_route_activation"]


def get_route_external_variables(model):
    """Return a dict mapping route external variable names to their 0/1 activation state.

    Designed for DSDA enumeration so that each route can be treated as an external (discrete)
    decision without rebuilding the model.

    Parameters
    ----------
    model : ConcreteModel
        Built via build_fermentation_model(include_kinetics=True).

    Returns
    -------
    dict
        { 'route_active_G': 0/1, ... }
    """
    if not hasattr(model, 'route_config'):
        raise AttributeError("Model does not define route_config (build with include_kinetics=True)")
    return {f"route_active_{r}": int(model.route_config[r].value) for r in model.route_config}

__all__.append("get_route_external_variables")


def set_routes_activation(model, route_map):
    """Bulk toggle multiple routes.

    Parameters
    ----------
    route_map : dict {route_name: bool/int}
        Values interpreted truthily: 1/True activate, else deactivate.
    """
    for r, val in route_map.items():
        set_route_activation(model, r, bool(val))

__all__.append("set_routes_activation")


def optimize_routes_local_descent(model, evaluator, max_iters=20, cache=True, tabu_length=0, logger=None):
    """Run local descent (1-flip neighborhood) over route activation vector on an existing model.

    Features:
    - Optional result caching (avoids re-evaluating repeated vectors).
    - Simple tabu list (prevents revisiting last N accepted vectors).
    - Structured logging hook per improvement iteration.

    Parameters
    ----------
    model : ConcreteModel
        Must define model.route_config with binary-like (0/1) mutable Params.
    evaluator : callable(dict)-> (objective_value: float, feasible: bool)
        Receives a dict {route_name:0/1}. Must be deterministic for caching validity.
    max_iters : int
        Max improvement iterations (loop stops early if no improving neighbor).
    cache : bool
        Enable memoization of evaluated vectors.
    tabu_length : int
        If >0 keeps a FIFO list of recently accepted vectors (hash) to skip.
    logger : callable(dict) or logging.Logger, optional
        If provided, called with info dict on each accepted improvement.

    Returns
    -------
    dict
        keys: best_vector, best_value, iterations, history, evaluated_count, cache_hits
    """
    try:
        from biorefinery.optimization.dsda_adapter import (
            extract_route_vector,
            one_flip_neighbors,
            evaluate_vector,
            steepest_improvement_step,
            run_local_descent,
        )
    except ImportError:  # fallback relative
        from ..optimization.dsda_adapter import (
            extract_route_vector,
            one_flip_neighbors,
            evaluate_vector,
            steepest_improvement_step,
            run_local_descent,
        )

    # Implement a simplified in-place local descent loop because the generic
    # run_local_descent() utility expects model_builder kwargs, not an existing model.
    current_list = extract_route_vector(model)
    routes = list(model.route_config.keys())
    def list_to_dict(lst):
        return {r: lst[i] for i, r in enumerate(routes)}
    current = list_to_dict(current_list)
    def vec_key(d):
        return tuple(int(d[r]) for r in routes)
    cache_dict = {}
    tabu = []
    evaluated = 0
    cache_hits = 0
    def evaluate(state):
        nonlocal evaluated, cache_hits
        k = vec_key(state)
        if cache and k in cache_dict:
            cache_hits += 1
            return cache_dict[k]
        val, feas = evaluator(state)
        evaluated += 1
        if cache:
            cache_dict[k] = (val, feas)
        return val, feas

    best_val, feasible = evaluate(current)
    history = [(current.copy(), best_val)]
    if not feasible:
        return {"best_vector": current, "best_value": best_val, "iterations": 0, "history": history,
                "evaluated_count": evaluated, "cache_hits": cache_hits}
    if tabu_length > 0:
        tabu.append(vec_key(current))
    for it in range(max_iters):
        improved = False
        # Generate one-flip neighbors
        for neighbor_list in one_flip_neighbors(list(current.values())):
            neighbor = list_to_dict(neighbor_list)
            if tabu_length > 0 and vec_key(neighbor) in tabu:
                continue
            val, feas = evaluate(neighbor)
            history.append((neighbor.copy(), val))
            if feas and val < best_val - 1e-12:  # strict improvement
                current = neighbor
                best_val = val
                improved = True
                if tabu_length > 0:
                    tabu.append(vec_key(current))
                    if len(tabu) > tabu_length:
                        tabu.pop(0)
                if logger:
                    log_payload = {"iteration": it, "best_value": best_val, "vector": current.copy(),
                                   "evaluated_count": evaluated, "cache_hits": cache_hits}
                    try:
                        if hasattr(logger, 'info'):
                            logger.info(log_payload)
                        else:
                            logger(log_payload)
                    except Exception:
                        pass
        if not improved:
            break
    return {"best_vector": current, "best_value": best_val, "iterations": len(history)-1, "history": history,
            "evaluated_count": evaluated, "cache_hits": cache_hits}

__all__.append("optimize_routes_local_descent")


def optimize_routes_multi_start(model, evaluator, starts=5, max_iters=20, seed=None,
                                cache=True, tabu_length=0, logger=None):
    """Run multiple local descent restarts from random initial route vectors.

    Parameters
    ----------
    starts : int or list[dict]
        If int, number of random starting vectors. If list, each element is a dict route->0/1.
    seed : int, optional
        Random seed for reproducible starts.
    Remaining params forwarded to optimize_routes_local_descent.

    Returns
    -------
    dict
        keys: best_overall, runs (list of per-start results)
    """
    import random
    routes = list(model.route_config.keys())
    rng = random.Random(seed)

    start_vectors = []
    if isinstance(starts, int):
        for _ in range(starts):
            start_vectors.append({r: rng.choice([0,1]) for r in routes})
    else:
        start_vectors = starts

    runs = []
    best_global = None
    best_val = None
    # Save current state to restore after each start
    saved_state = {r: int(model.route_config[r].value) for r in routes}
    for sv in start_vectors:
        # Apply start
        for r, v in sv.items():
            model.route_config[r] = v
        res = optimize_routes_local_descent(model, evaluator, max_iters=max_iters,
                                            cache=cache, tabu_length=tabu_length, logger=logger)
        res['start_vector'] = sv
        runs.append(res)
        if best_val is None or res['best_value'] < best_val:
            best_val = res['best_value']
            best_global = res['best_vector']
    # Restore original state
    for r, v in saved_state.items():
        model.route_config[r] = v
    return {"best_overall": best_global, "best_value": best_val, "runs": runs}

__all__.append("optimize_routes_multi_start")
