"""External variable reformulation utilities.

Contains logic helpers and transformation routines extracted from the legacy
Fermentation_Scheduling_and_MPC script. Pure functions only; no side-effects
besides Pyomo model mutation.
"""
from __future__ import annotations
import pyomo.environ as pe
import pyomo.environ as pe
from pyomo.common.errors import InfeasibleConstraintException  # noqa: F401 (may be used elsewhere)
from typing import Dict, List, Any


def dummy_logic(m) -> List[list]:
    logic_expr = []
    for n in m.set1:
        logic_expr.append([m.Y1[n], m.Y1_disjunct[n].indicator_var])
    for n in m.set2:
        logic_expr.append([m.Y2[n], m.Y2_disjunct[n].indicator_var])
    return logic_expr


def dummy_logic_v2(m) -> List[list]:
    logic_expr = []
    for r in m.react_set:
        for n in m.set1[r]:
            logic_expr.append([m.Y1[r][n], m.Y1_disjunct[r][n].indicator_var])
        for n in m.set2[r]:
            logic_expr.append([m.Y2[r][n], m.Y2_disjunct[r][n].indicator_var])
    return logic_expr


def get_external_information(m: pe.ConcreteModel, ext_ref, tee: bool = False):
    """Collect structural information for external variable reformulation.

    Returns tuple: (reformulation_dict, number_of_external_variables, lower_bounds, upper_bounds)
    """
    try:
        ref_index = {}
        no_ref_index = {}
        for i in ext_ref:
            ref_index[i] = []
            no_ref_index[i] = []
            for index_set in range(len(i.index_set()._sets)):
                if i.index_set()._sets[index_set].name == ext_ref[i].name:
                    ref_index[i].append(index_set)
                else:
                    no_ref_index[i].append(index_set)
    except Exception:
        ref_index = {}
        no_ref_index = {}
        for i in ext_ref:
            ref_index[i] = []
            no_ref_index[i] = []
            if i.index_set().name == ext_ref[i].name:
                ref_index[i].append(0)
            else:
                no_ref_index[i].append(0)

    count = 1
    reformulation_dict: Dict[int, Dict[str, Any]] = {}
    for c in m.component_data_objects(pe.LogicalConstraint, descend_into=True):
        if c.body.getname() == 'exactly':
            exactly_number = c.body.args[0]
            for possible_Boolean in ext_ref:
                expected_Boolean = possible_Boolean.name
                Boolean_name_list = [c.body.args[1:][k]._component()._name for k in range(len(c.body.args[1:]))]
                if all(x == expected_Boolean for x in Boolean_name_list):
                    expected_ordered_set_index = ref_index[possible_Boolean]
                    index_of_other_sets = no_ref_index[possible_Boolean]
                    if len(index_of_other_sets) >= 1:
                        Other_Sets_listOFlists = []
                        verification_Other_Sets_listOFlists = []
                        for j in index_of_other_sets:
                            Other_Sets_listOFlists.append([
                                c.body.args[1:][k].index()[j] for k in range(len(c.body.args[1:]))
                            ])
                            if all(c.body.args[1:][x].index()[j] == c.body.args[1:][0].index()[j] for x in range(len(c.body.args[1:]))):
                                verification_Other_Sets_listOFlists.append(True)
                            else:
                                verification_Other_Sets_listOFlists.append(False)
                        if all(verification_Other_Sets_listOFlists):
                            reformulation_dict[count] = {}
                            reformulation_dict[count]['exactly_number'] = exactly_number
                            sorted_args = sorted(c.body.args[1:], key=lambda x: x.index()[expected_ordered_set_index[0]])
                            reformulation_dict[count]['Boolean_vars_names'] = [
                                sorted_args[k].name for k in range(len(sorted_args))
                            ]
                            reformulation_dict[count]['Boolean_vars_ordered_index'] = [
                                sorted_args[k].index()[expected_ordered_set_index[0]] for k in range(len(sorted_args))
                            ]
                            reformulation_dict[count]['Ext_var_lower_bound'] = 1
                            reformulation_dict[count]['Ext_var_upper_bound'] = len(sorted_args)
                            count += 1
                    else:
                        reformulation_dict[count] = {}
                        reformulation_dict[count]['exactly_number'] = exactly_number
                        sorted_args = sorted(c.body.args[1:], key=lambda x: x.index())
                        reformulation_dict[count]['Boolean_vars_names'] = [sorted_args[k].name for k in range(len(sorted_args))]
                        reformulation_dict[count]['Boolean_vars_ordered_index'] = [
                            sorted_args[k].index() for k in range(len(sorted_args))
                        ]
                        reformulation_dict[count]['Ext_var_lower_bound'] = 1
                        reformulation_dict[count]['Ext_var_upper_bound'] = len(sorted_args)
                        count += 1

    number_of_external_variables = sum(reformulation_dict[j]['exactly_number'] for j in reformulation_dict)
    lower_bounds = {}
    upper_bounds = {}
    exvar_num = 1
    for i in reformulation_dict:
        for _ in range(reformulation_dict[i]['exactly_number']):
            lower_bounds[exvar_num] = reformulation_dict[i]['Ext_var_lower_bound']
            upper_bounds[exvar_num] = reformulation_dict[i]['Ext_var_upper_bound']
        exvar_num += 1

    if tee:
        print('\nReformulation Summary\n--------------------------------------------------------------------------')
        exvar_num = 0
        for i in reformulation_dict:
            for _ in range(reformulation_dict[i]['exactly_number']):
                print(
                    'External variable x['+str(exvar_num)+'] is associated to '+str(reformulation_dict[i]['Boolean_vars_names'])+
                    ' and it must be within '+str(reformulation_dict[i]['Ext_var_lower_bound'])+' and '+str(reformulation_dict[i]['Ext_var_upper_bound'])+'.'
                )
                exvar_num += 1
        print('\nThere are '+str(number_of_external_variables)+' external variables in total')

    return reformulation_dict, number_of_external_variables, lower_bounds, upper_bounds


def external_ref(m: pe.ConcreteModel, x, extra_logic_function, dict_extvar: dict = {}, mip_ref: bool = False,
                 transformation: str = 'bigm', tee: bool = False):
    # Re-bind Boolean / (optional) Binary vars by name
    for i in dict_extvar:
        dict_extvar[i]['Boolean_vars'] = []
        for j in dict_extvar[i]['Boolean_vars_names']:
            for boolean in m.component_data_objects(pe.BooleanVar, descend_into=True):
                if boolean.name == j:
                    dict_extvar[i]['Boolean_vars'].append(boolean)
        if mip_ref:
            dict_extvar[i]['Binary_vars'] = []
            for j in dict_extvar[i].get('Binary_vars_names', []):
                for binary in m.component_data_objects(pe.Var, descend_into=True):
                    if binary.name == j:
                        dict_extvar[i]['Binary_vars'].append(binary)

    ext_var_position = 0
    for i in dict_extvar:
        for _ in range(dict_extvar[i]['exactly_number']):
            for k in range(1, len(dict_extvar[i]['Boolean_vars'])+1):
                if x[ext_var_position] == k:
                    if not mip_ref:
                        dict_extvar[i]['Boolean_vars'][k-1].fix(True)
                    else:
                        dict_extvar[i]['Binary_vars'][k-1].fix(1)
                        dict_extvar[i]['Boolean_vars'][k-1].set_value(True)
            ext_var_position += 1
        for _ in range(dict_extvar[i]['exactly_number']):
            for k in range(1, len(dict_extvar[i]['Boolean_vars'])+1):
                if not mip_ref:
                    if not dict_extvar[i]['Boolean_vars'][k-1].is_fixed():
                        dict_extvar[i]['Boolean_vars'][k-1].fix(False)
                else:
                    if not dict_extvar[i]['Binary_vars'][k-1].is_fixed():
                        dict_extvar[i]['Binary_vars'][k-1].fix(0)
                        dict_extvar[i]['Boolean_vars'][k-1].set_value(False)

    logic_expr = extra_logic_function(m)
    for expr, var in logic_expr:
        if not mip_ref:
            var.fix(pe.value(expr))
        else:
            var.set_value(pe.value(expr))

    pe.TransformationFactory('core.logical_to_linear').apply_to(m)
    if mip_ref:
        pe.TransformationFactory('gdp.' + transformation).apply_to(m)
    else:
        pe.TransformationFactory('gdp.fix_disjuncts').apply_to(m)
    pe.TransformationFactory('contrib.deactivate_trivial_constraints').apply_to(m, tmp=False, ignore_infeasible=True)

    if tee:
        print('\nFixed variables at current iteration:\n')
        print('\n Independent Boolean variables\n')
        for i in dict_extvar:
            for k in range(1, len(dict_extvar[i]['Boolean_vars'])+1):
                print(dict_extvar[i]['Boolean_vars_names'][k-1] + '=' + str(dict_extvar[i]['Boolean_vars'][k-1].value))
        print('\n Dependent Boolean variables and disjunctions\n')
        for _, var in logic_expr:
            print(var.name + '=' + str(var.value))
        if mip_ref:
            print('\n Independent binary variables\n')
            for i in dict_extvar:
                for k in range(1, len(dict_extvar[i]['Binary_vars'])+1):
                    print(dict_extvar[i]['Binary_vars_names'][k-1] + '=' + str(dict_extvar[i]['Binary_vars'][k-1].value))

    return m

def extvars_gdp_to_mip(m, gdp_dict_extvar, transformation='bigm'):
    """Minimal placeholder for external variable GDP→MIP transformation.

    Currently returns the model and dictionary unchanged to avoid breaking
    enumeration flows when mip_transformation=True is accidentally set.

    Parameters
    ----------
    m : ConcreteModel
        Pyomo model (GDP or already transformed)
    gdp_dict_extvar : dict
        Mapping of external variable groups
    transformation : str
        Name of GDP transformation (ignored in stub)

    Returns
    -------
    (m, gdp_dict_extvar)
        Unmodified inputs.
    """
    # Future: apply pe.TransformationFactory(f'gdp.{transformation}')
    return m, gdp_dict_extvar
