import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import numpy as np
import pyomo.environ as pyo
import gsheetsdb as gs
from pyomo.environ import *
from pyomo.opt import SolverFactory
from gsheetsdb import connect


st.title("Prescriptive Analitics")
st.subheader("Decision Optimization")
st.write(pyomo.version.version_info)

model = pyo.ConcreteModel()
model.x = pyo.Var(range(3),bounds=(1,10), within=Integers)
model.y = pyo.Var(range(3),bounds=(0,10))
x = model.x
y = model.y
model.obj = pyo.Objective(expr = sum(x[i]+y[i] for i in range(3)))
model.c = pyo.Constraint(expr = x[0]>=3)

st.write(model.x.pprint('glpk'))
opt = SolverFactory()
results = opt.solve(model, tee=True)
st.write(results)

st.write('---------------------#########----------')
st.write(results.solver.status)
st.write(results.write())