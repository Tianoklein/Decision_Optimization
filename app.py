# STREAMLIT
import streamlit as st

# PYOMO
import pyomo.environ as pyo
from pyomo.environ import *
from pyomo.opt import SolverFactory

# PANDAS
import pandas as pd

# GOOGLE AUTH
from google.oauth2 import service_account

# GSPREAD
import gspread as gs

import locale
locale.setlocale(locale.LC_ALL, 'pt_BR')

st.set_page_config(
     page_title="Prescritive Analytics / Analise de Sugestão",
     page_icon="🧊",
     layout="wide",
     initial_sidebar_state="expanded",
)


### ACESSO AS PLANILHAS DO GOOGLE:
scopes = ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive']
def login():
    '''
    FAZ O LOGIN NO GOOGLE DOCS USANDO CREDENCIAIS GCP
    '''
    credentials = service_account.Credentials.from_service_account_info(st.secrets["gcp_service_account"])
    scoped_credentials = credentials.with_scopes(scopes)
    gc = gs.authorize(scoped_credentials)
    return gc

def df_to_spreadsheet(spreadsheets,aba, df):
    '''
    Carrega um Dataframe em uma planilha do GDocs
    spreadsheets = nome da planilha
    aba = Aba do excel
    df  = Dataframe
    '''
    gc = login()
    spreadsheet = gc.open(spreadsheets)
    wks = spreadsheet.worksheet(aba)
    wks.clear()
    data_list = df.values.tolist()
    wks.insert_rows(data_list)
    #header = ["Maq","Prod","Cliente","QtdProduction","Days","VALIDAÇAO","Custo_por_Ton","Capacidade_Max_por_dia","Valor_Frete","QtdContainers","ValorDeliveryTotal","Valor Total de Produção SEM FRETE","Model OF"]
    wks.insert_row(df.columns.tolist(), 1)

def df_from_spreadsheet(spreadsheets,aba):
    '''
    Carrega um Dataframe de uma planilha do GDocs
    spreadsheets = nome da planilha
    aba = Aba do excel
    retorna: Dataframe
    '''
    gc = login()
    spreadsheet = gc.open(spreadsheets)
    wks = spreadsheet.worksheet(aba)
    data = wks.get_all_values()
    headers = data.pop(0)
    df = pd.DataFrame(data, columns=headers)
    df = df.set_index(aba)
    df.index.name = None
    df = df.apply(lambda x: x.str.replace(',','.'))
    for column in df.columns:
        df[column] = pd.to_numeric(df[column])
    return df

def roda_algoritmo(container, dias):
    ### CAPACIDADE
    df_capacidade = df_from_spreadsheet("pyomo","CAPACIDADE")
    df_capacidade = df_capacidade.fillna(1)
    ### CUSTO
    df_custo = df_from_spreadsheet("pyomo","CUSTO")
    df_custo = df_custo.fillna(10000000)
    ### DEMANDA
    df_demanda = df_from_spreadsheet("pyomo","DEMANDA")
    df_demanda = df_demanda.fillna(0)
    ### FRETE
    df_frete = df_from_spreadsheet("pyomo","FRETE")
    df_frete = df_frete.fillna(0)
    df_frete = df_frete.T
 
    ### ALGORITMO DE OTIMIZAÇÃO:
    model = ConcreteModel()
    model.i = df_custo.keys()    ## i=Machines
    model.j = df_demanda.index   ## j=Products
    model.h = df_demanda.keys()  ## h=Customers

    model.x = Var(model.i, model.j,model.h, within=NonNegativeReals) 
    model.y = Var(model.i, model.j,model.h, bounds=(0,dias),  within=NonNegativeReals)
    model.OF = Var(within=Reals)                  ### Total production Cost
    model.P = Var(model.i,within=Reals)           ### Production by Machin  
    def rule_C0(model, i):
        return sum(model.x[i,j,h] for j in model.j for h in model.h) == model.P[i]
    model.C0 = Constraint(model.i, rule=rule_C0)
    model.C1 = ConstraintList()
    for j in model.j:
        for h in model.h:
            if df_demanda.loc[j,h] > 0:
                model.C1.add(sum(model.x[i,j,h] for i in model.i) == (df_demanda.loc[j,h] ) )
    model.C2 = ConstraintList()
    for i in model.i:
        for j in model.j:
            for h in model.h:
                model.C2.add(model.x[i,j,h] == (df_capacidade.loc[j,i] * model.y[i,j,h]) )
    model.C01 = ConstraintList() # DIAS_TOTAL
    for i in model.i:
        model.C01.add(sum(model.y[i,j,h] for h in model.h for j in model.j) <= dias)

    def rule_OF(model):                          
        return model.OF == sum(
            (model.x[i,j,h] * df_custo.loc[j,i])
            +
            (
                (model.x[i,j,h] / container) 
                * 
                df_frete.loc[i,h]) for i in model.i for j in model.j for h in model.h)

    model.C3 = Constraint(rule=rule_OF)
    model.obj1 = Objective(expr=model.OF, sense=minimize)
    solver = SolverFactory('glpk')
    results = solver.solve(model, tee=True)
    vOF = value(model.OF)
    print(results)
    print("OF= ",vOF )

    df = pd.DataFrame(columns=('Maq','Prod', 'Cliente', 'QtdProduction', 'Days',"VALIDAÇAO","Custo_por_Ton", "Capacidade_Max_por_dia", "Valor_Frete", "QtdContainers", "ValorDeliveryTotal", "Valor Total de Produção SEM FRETE", 'Model OF' ) )
    for i in model.i:
        for j in model.j:
            for h in model.h:
                v1 = value(model.x[i,j,h])
                v2 = value(model.y[i,j,h]) 
                v3 = value(df_custo.loc[j,i])
                v4 = value(df_capacidade.loc[j,i])
                v41 = value(df_frete.loc[i,h])
                v5  = ( v1 / container) 
                v6 = ( v1 / container) * df_frete.loc[i,h]
                v7 = (v1 * v3)
                v8 = (v1 * v3) + v6 
                if v1>0:
                    #model.x[i,j,h] * custo[i][j]
                    #print (i, j, h, v1, v2, v3,v4)
                    df = df.append(pd.DataFrame({"Maq":[i], "Prod":[j], "Cliente":[h], "QtdProduction":[v1], "Days":[v2], "Custo_por_Ton": v3,
            "Capacidade_Max_por_dia": v4,"Valor_Frete": v41, "QtdContainers" : v5, "ValorDeliveryTotal" : v6, "Valor Total de Produção SEM FRETE": v7, "Model OF": v8}))
    return(df,vOF)





####INTERFACE:
def main():
    """"Prescritive Analytics / Analise de Sugestão"""
    st.title("Prescritive Analytics / Analise de Sugestão")
    menu = ["HOME", "II - Linha de Produção", "ITEM2", "SOBRE"]
    choice = st.sidebar.selectbox("Menu", menu)



    if choice == "HOME":
        st.subheader("Faz a sugestão de recomendação")
        st.subheader("Recomendação...")


    elif choice == "II - Linha de Produção":
        ###----------------------------------------####
        st.write("Preencha os valores na planilha abaixo:")
        st.write("CAPACIDADE: Produção em cada uma das Máquinas em 1 periodo de tempo")
        st.write("CUSTO: Produção em cada uma Máquina em 1 periodo de tempo")
        st.write("DEMANDA: Demanda de produtos pelos Clientes")
        st.write("Frete: Para envio da Quantidade do Produto A pela Máquina X")

        col1, col2 = st.beta_columns(2)
        with col1:
            st_dias = st.number_input('Periodo para Atingir a Demanda:' , value=30)
        with col2:
             st_containers = st.number_input('Qtd maxima por pacote:',value=25)
        
        
        # embed streamlit docs in a streamlit app
        import streamlit.components.v1 as components
        components.iframe(st.secrets["private_gsheets_url"],width=1300, height=800)
        
        if st.button("Enviar"):
            ####----------------------------------------####
            st.subheader("DATAFRAME RESULTADO RECOMENDAÇÃO")
            st.write(st_dias)
            st.write(st_containers)
            ## cria o dataframe com o resultado da sugestao:
            df,vOF =  roda_algoritmo(st_containers, st_dias)
            st.write("Custo total para fabricação da Demanda:", locale.currency(vOF,grouping=True))
            st.dataframe(df)

            df.fillna('', inplace=True)
            df_to_spreadsheet("pyomo","RESULTADO",df)

    if choice == "SOBRE":
        st.subheader("Sobre...")
        if st.button("OBRIGADO!!!"):
            st.balloons()
        
        st.info("Desenvolvido por Paulo Cristiano Klein, com ajuda de muitos amigos!\n\n"
                "Mantido por [Paulo Klein](https://www.linkedin.com/in/pauloklein/). "
                  "Me visite também em https://github.com/Tianoklein")
        
        html_temp = '''<a href="mailto:tianoklein@hotmail.com?subject=Streamlit NFC-E Parse&body=Tenho uma sugestão: ">  Duvidas, criticas e sugestões </a>'''

        import streamlit.components.v1 as components
        components.html(html_temp)   
        


if __name__ == '__main__':
    main()




