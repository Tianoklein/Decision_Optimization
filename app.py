import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import numpy as np
import pyomo.environ as pyo
import gsheetsdb as gs
from pyomo.environ import *
from pyomo.opt import SolverFactory
import time
from gsheetsdb import connect


st.title("Prescriptive Analitics")
st.subheader("Decision Optimization")
st.write(pyomo.version.version_info)

model = pyo.ConcreteModel()
model.x = pyo.Var(bounds=(-np.inf,3))
model.y = pyo.Var(bounds=(0,np.inf))

x = model.x
y = model.y
model.C1 = pyo.Constraint(expr= x+y<=8)
model.C2 = pyo.Constraint(expr= 8*x+3*y>=-24)
model.C3 = pyo.Constraint(expr= -6*x+8*y<=48)
model.C4 = pyo.Constraint(expr= 3*x+5*y<=15)

model.obj = pyo.Objective(expr= -4*x-2*y, sense=minimize)

tempo_inicial = time.time()
opt = SolverFactory('glpk')
results = opt.solve(model, tee=True)
st.write(results)
tempo = time.time()-tempo_inicial

x_value = pyo.value(x)
y_value = pyo.value(y)

st.write('---------------------#########----------')
st.write('tempo:',tempo)
st.write('x:',x_value)
st.write('y:',y_value)
