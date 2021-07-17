# STREAMLIT
from numpy import empty
import streamlit as st
import plotly.express as px

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


### CONFIGURAÇÕES GERAIS:
locale.setlocale(locale.LC_ALL, 'pt_BR')
st.set_page_config(
     page_title="Prescritive Analytics / Análise de Sugestão",
     page_icon="random",
     layout="wide",
     initial_sidebar_state="expanded",
)


### ACESSO AS PLANILHAS DO GOOGLE: GRACIAS![https://medium.com/pyladiesbh/gspread-trabalhando-com-o-google-sheets-f12e53ed1346]
def login():
    '''
    FAZ O LOGIN NO GOOGLE DOCS USANDO CREDENCIAIS GCP
    '''
    scopes = ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive']
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

    model.x = Var(model.i, model.j,model.h, within=NonNegativeReals)                    ### Quantity
    model.y = Var(model.i, model.j,model.h, bounds=(0,dias),  within=NonNegativeReals)  ### Days
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
    #print(results)
    #print("OF= ",vOF )

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



#### INTERFACE:
def main():
    st.title("Prescritive Analytics / Análise de Sugestão / Pesquisa Operacional")
    menu = ["HOME", "I - Linha de Produção Simples", "II - Linha de Produção Elaborada", "III - Carteira de Investimentos", "SOBRE"]
    choice = st.sidebar.selectbox("Menu", menu)


#### HOME:
    if choice == "HOME":
        st.write("Faz a sugestão de recomendação... Disseminar conhecimento sobre Prescritive Analytics /  Analise de sugestão ou Recomendação")
        st.write("Objetivo: Demonstrar o potencial de soluções que utilizam PO para tomada de decisão")
        
        st.subheader("Linha de Produção Simples")
        st.write("Objetivo: Demonstrar o potencial de soluções que utilizam PO para tomada de decisão")
        
        st.subheader("Linha de Produção Elaborada")
        st.write("Objetivo: Demonstrar o potencial de soluções que utilizam PO para tomada de decisão")

        st.subheader("Carteira de Investimentos")
        st.write("Objetivo: Demonstrar o potencial de soluções que utilizam PO para tomada de decisão")


#### MIX DE PRODUÇÃO - SIMPLES:
    if choice == "I - Linha de Produção Simples":
        st.subheader("Faz a sugestão de em uma linha de produção simples: Uma Padaria.")
        st.write("Objetivo: Demonstrar")
        st.subheader("Recomendação...")

#### MIX DE PRODUÇÃO - ELABORADO:
    elif choice == "II - Linha de Produção Elaborada":
        with st.beta_expander("Objetivo:"):
            st.write("Minimizar o custo de produção incluindo o valor do frete, que é um valor fixo por capacidade maxima por pacote. \n \n \
- Quantidade de produção x Custo de produção + Valor do Frete por embalagem.  \n  \
- A demanda precisa ser igual a quantidade que deverá ser produzida  \n \
- A capacidade de produção diária precisa ser respeitada")
            st.write("Resultado: É quantidade de dias necessária, bem como a melhor alocação das máquinas, para minimizar o custo de produção da demanda" )

        st.write("Preencha os valores na planilha conforme abaixo:")
        col1, col2, col3 = st.beta_columns(3)
        with col1:
            st.write("**CAPACIDADE**: Produção em cada Máquina em 1 periodo de tempo")
            st.write("**CUSTO**: Produção em cada uma Máquina em 1 periodo de tempo")
        with col2:    
            st.write("**DEMANDA**: Demanda de produtos pelos Clientes")
            st.write("**FRETE**: Valor para envio da Quantidade do Produto A pela Máquina X")
        
        col1, col2, col3 = st.beta_columns(3)
        with col1:
            st_dias = st.number_input('Periodo para Atingir a Demanda:' , value=30)
        with col2:
             st_containers = st.number_input('Quantidade maxima de itens por pacote(frete):',value=25)
        
        # embed streamlit docs in a streamlit app
        import streamlit.components.v1 as components
        components.iframe(st.secrets["private_gsheets_url"],width=1500, height=800)
        
        if st.button("Enviar"):
            st.subheader("DATAFRAME RESULTADO RECOMENDAÇÃO")
            st.write(st_dias)
            st.write(st_containers)
            ## cria o dataframe com o resultado da sugestao:
            df,vOF =  roda_algoritmo(st_containers, st_dias)
            st.write("Custo total para fabricação da Demanda:", locale.currency(vOF,grouping=True))
            st.dataframe(df)
            df.fillna('', inplace=True)
            df_to_spreadsheet("pyomo","RESULTADO",df)

            #### GRÁFICOS:
            fig = px.bar(df.groupby(['Maq']).agg({'Days': 'sum'}))
            fig.update_layout(title = "Utilização das Maquinas",width=1500, height=800)
            st.plotly_chart(fig)
            fig = px.bar(df, x='Maq', y='QtdProduction', color='Cliente', barmode ='stack')
            fig.update_layout(title = "Qtd de Produção por Máquina",width=1500, height=800)
            st.plotly_chart(fig)
            fig = px.bar(df, x='Maq', y='Days', color='Cliente', barmode ='stack')
            fig.update_layout(title = "Tempo de Producão por Cliente",width=1500, height=800)
            st.plotly_chart(fig)
            fig = px.bar(df, x='Maq', y='Days', color='Prod', barmode   ='stack')
            fig.update_layout(title = "Tempo de Producão por Produto",width=1500, height=800)
            st.plotly_chart(fig)    


            





#### CARTEIRA DE INVESTIMENTOS:    
    elif choice == "III - Carteira de Investimentos":
        st.subheader("Carteira de Investimentos...")    



#### SOBRE:    
    elif choice == "SOBRE":
        col1, col2, col3, col4= st.beta_columns(4)
        with col1:
            with st.beta_expander("Fonte"):
                st.write(
                        """
                        - Livros:
                        - Revistas:
                        ...
                        """  )



        st.subheader("Sobre...\
                       AAAAA AAAA \
                        AAAAA")
        if st.button("OBRIGADO!!!"):
            st.balloons()
        
        st.info("Desenvolvido por Paulo Cristiano Klein, com ajuda de muitos amigos!\n"
                "Mantido por [Paulo Klein](https://www.linkedin.com/in/pauloklein/). "
                "Me visite também em https://github.com/Tianoklein")
        html_temp = '''<a href="mailto:tianoklein@hotmail.com?subject=Streamlit DO/PO Parse&body=Tenho uma sugestão: ">  Duvidas, criticas e sugestões </a>'''
        import streamlit.components.v1 as components
        components.html(html_temp)

if __name__ == '__main__':
    main()