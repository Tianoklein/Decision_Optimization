import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import numpy as np
import pyomo.environ as pyo
import gsheetsdb as gs
from pyomo.environ import *
from pyomo.opt import SolverFactory
from gsheetsdb import connect


st.subheader("IFRAME")
components.iframe(
'''
<iframe src="https://docs.google.com/spreadsheets/d/e/2PACX-1vQygBicNaTXHGVFdYbK9RooQlexyw2qoe0RDnVv7lh7JvWvwhYz_aB3ARX8s38U96IfPXDZvYCUgKlG/pubhtml?widget=true&amp;headers=false"></iframe>
''')

conn = connect()
# Perform SQL query on the Google Sheet.
# Uses st.cache to only rerun when the query changes or after 10 min.
@st.cache(ttl=600)
def run_query(query):
    rows = conn.execute(query, headers=1)
    return rows

sheet_url = st.secrets["public_gsheets_url"]
rows = run_query(f'SELECT * FROM "{sheet_url}"')

# Print results.
for row in rows:
    st.write(f"{row.name} has a :{row.pet}:")



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

st.write(model.x.pprint())
opt = SolverFactory('glpk')
results = opt.solve(model, tee=True)
st.write(results)

st.write('---------------------#########----------')
st.write(results.solver.status)
st.write(results.write())