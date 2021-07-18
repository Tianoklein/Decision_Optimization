# STREAMLIT
import streamlit as st
# DASHBOARD
import plotly.express as px
import random
from wordcloud import WordCloud

# PANDAS
import pandas as pd
# PYOMO
import pyomo.environ as pyo
from pyomo.environ import *
from pyomo.opt import SolverFactory
# GOOGLE AUTH
from google.oauth2 import service_account
# GSPREAD
import gspread as gs
# CURRENCY
import locale

### CONFIGS:
locale.setlocale(locale.LC_ALL, 'pt_BR')
st.set_page_config(
     page_title="Prescritive Analytics / Análise de Sugestão",
     page_icon="random",
     layout="wide",
     initial_sidebar_state="expanded",
)

### ACESSO AS PLANILHAS DO GOOGLE: 
##GRACIAS![https://medium.com/pyladiesbh/gspread-trabalhando-com-o-google-sheets-f12e53ed1346]

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
    retorna: Dataframe previamente formatado
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
    '''
    roda o algoritmo de sugestao
    container = quantidade de itens no pacote(frete)
    dias = quantidade de dias para fabricacao da demanda
    '''
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
    print(results)
    print("RESULTADO:", results.solver.termination_condition)
    vOF = value(model.OF)
    #print("OF= ",vOF )
    columns1=('Maq','Prod', 'Cliente', 'QtdProduction', 'Days',"VALIDAÇAO","Custo_por_Ton", "Capacidade_Max_por_dia", "Valor_Frete", "QtdContainers", "ValorDeliveryTotal", "Valor Total de Produção SEM FRETE", 'Model OF')
    df = pd.DataFrame(columns = columns1)
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



#### UX:
def main():
    st.title("Prescritive Analytics / Análise de Sugestão / Pesquisa Operacional")
    menu = ["HOME", "I - Linha de Produção Simples", "II - Linha de Produção Elaborada", "III - Carteira de Investimentos", "SOBRE"]
    choice = st.sidebar.selectbox("Menu", menu)


#### HOME:
    if choice == "HOME":
        st.markdown('''
                    O objetivo é demonstrar de forma prática os conceitos em torno das soluções que utilizam ferramentas de uma área da 
                    **Inteligência Artificial** chamada de **Análise de Sugestão**, utilizada para tomada de decisão onde existen grandes quantidade de opções.
                    ''')
        with st.beta_expander("Conceitos:"):
                   st.markdown(
                  '''
                    A **Análise de Sugestão/Recomendação/Prescritiva** é utilizada para obtenção da melhor solução de todas as soluções viáveis 
                   a fim de atingir um objetivo levando em consideração algumas restrições. Um problema de otimização consiste em *maximizar* 
                   ou *minimizar* uma função objetivo, e encontrar a melhor solução de todas as soluções viáveis.

                   A tecnologia de **Análise Prescritiva** recomenda ações com base nos resultados desejados, levando em consideração cenários 
                   específicos, recursos e conhecimento de eventos passados e atuais. Esses insights podem ajudar sua organização à tomar 
                   melhores decisões e ter maior controle dos resultados  os negócios. A **Análise Prescritiva** fornece às organizações  
                   recomendações sobre as ações ideais para atingir os objetivos de negócios, como satisfação do cliente, lucros e economia 
                   de custos.

                   As soluções de **Análise Prescritiva** usam tecnologia de otimização para resolver decisões complexas com milhões de variáveis 
                   de decisão, restrições e regulagens. Organizações em dos os setores usam análises prescritivas para uma variedade de casos
                   de uso que abrangem o planejamento estratégico, atividades operacionais e táticas. A **Análise Prescritiva** é a próxima etapa 
                   no caminho para ações baseadas em  insights. Ele cria valor por meio da  sinergia com a **Análise PREDITIVA**, que analisa os 
                   dados do passado para prever resultados futuros. A **Análise Prescritiva** leva esse insight para o próximo nível, sugerindo a 
                   maneira ideal de lidar com essa situação futura. Organizações que podem agir rapidamente em condições dinâmicas e tomar decisões 
                   superiores em ambientes incertos ganham uma forte vantagem competitiva. 
                   ''' )
        
        st.markdown("No Menu tem os seguintes exemplos:")
        st.markdown("   Linha de Produção Simples:  \n Objetivo: Exemplo simples de uma padaria para demostrar o potencial de soluções que utilizam PO para tomada de decisão")
        st.markdown("   Linha de Produção Elaborada:  \n Objetivo: Exemplo mais complexo, para Minimizar o custo de produção de vários produtos.")
        st.markdown("   Carteira de Investimentos:  \n Objetivo: Demonstrar o potencial de soluções que utilizam PO para tomada de decisão sugerindo ações para montar carteira de investimentos.")
        
        # WORDCLOUD
        # FUNCAO PARA DEFINICAO DA COR:
        def grey_color_func(word, font_size, position, orientation, random_state=None,**kwargs):
            return "hsl(0, 0%%, %d%%)" % random.randint(30, 100)
        text = '"Pesquisa Operacional","Engenharia de Produção","Simulação Estocástica","Otimização Combinatória","Optimization","Prescriptive Analytics","Operations Research","Mathematical Optimization for Business Problems"'
        # CRIA A IMAGEM COMO WORDCLOUD
        wordcloud = WordCloud(background_color='black', max_font_size = 40,collocations=False).generate(text)
        #change the color setting
        wordcloud.recolor(color_func = grey_color_func)
        # plot
        fig = px.imshow(wordcloud)
        fig.update_layout(coloraxis_showscale=False)
        fig.update_layout(width=1300, height=800)
        fig.update_xaxes(showticklabels=False)
        fig.update_yaxes(showticklabels=False)
        st.plotly_chart(fig) 


#### MIX DE PRODUÇÃO - SIMPLES:
    if choice == "I - Linha de Produção Simples":
        st.subheader("Produção de BOLOS e TORTAS em uma Padaria")
        st.write('''
        Quantos Bolos e Tortas devem ser feitos para maximizar o lucro desses dois produtos sob determinadas condições?
        ''')
        image = "https://bimbon-assets.s3.amazonaws.com/ckeditor/picture/data/52701fe1f369336f5300063f/content_Przystanek_bimbon03.jpg"
        st.image(image, width=370,)
        with st.beta_expander("Regras de Negócio:"):
            st.markdown(
                  '''
                  Uma padaria faz bolos e tortas todos os periodos. Há: 1 forno, 2 padeiros, 1 empacotador que trabalha apenas 22 periodos. 
                  O bolo requer o uso do forno por 1 periodo e a torta requer 0,5 periodo. Cada padeiro precisa trabalhar para o bolo 0,5 pariodos e para torta 2 periodos. 
                  O empacotador precisa trabalhar para o bolo 1 periodo e a torta 0,5 periodo. O lucro em cada bolo é R$ 15,00 e o lucro em cada torta é R$ 12,00. 
                   
                Exemplo de valores:
                    - 1 FORNO
                    - 2 PADEIRO
                    - 1 EMPACOTADOR que trabala 22 periodos.
                Tempo de Preparo:                    
                    - FORNO      = BOLO 1 periodo   + TORTA 0.5 periodo  <=30 periodos
                    - PADEIRO    = BOLO 0.5 periodo + TORTA 2.0 periodo  <=60 periodos ( 2 padeiros)
                    - EMPACOTAOR = BOLO 1.O periodo + TORTA 0.5 periodo  <=22 periodos
                    - LUCRO BOLO = 15
                    - LUCRO TORTA = 12
        Objetivo: Maximizar os Lucros com os dois produtos na linha de produção
                  ''')

        with st.beta_expander("Quantidade de produtos já vendidas dos produtos:"):

            col1, col2,col3 = st.beta_columns(3)
            with col1:
                minBOLO = st.number_input('BOLO - Qtd min :', help='Fabricação mimima de Bolo - já demandada' , value=0)
            with col2:
                minTORTA = st.number_input('TORTA - Qtd min:',  help='Fabricação mimima de Bolo - já demandada' , value=0)          
        with st.beta_expander("Valor de lucro  dos produtos:"):
            st.write("LUCRO:")
            col1, col2,col3 = st.beta_columns(3)
            with col1:
                LucroBOLO = st.number_input('BOLO - Margem de Lucro:', help='Margem de Lucro do Bolo' , value=15.00, format="%.2f")
            with col2:
                LucroTORTA = st.number_input('TORTA - Margem de Lucro:',  help='Margem de Lucro do Torta' , value=12.00, format="%.2f")
        with st.beta_expander("Restrições/Condições que precisam ser respeitadas:"):
            st.write("Capacidade - BOLO:")
            col1, col2, col3 = st.beta_columns(3)
            with col1:
                pFORNO = st.number_input('FORNO - Capacidade:', help='Capacidade máxima de tempo do FORNO em periodos' , value=30)
            with col2:
                pPADEIRO = st.number_input('PADEIRO - Capacidade:', help='Capacidade máxima de tempo do PADEIRO em periodos:', value=60)
            with col3:
                pEMPACOTADOR = st.number_input('EMPACOTADOR - Capacidade:', help='Capacidade máxima de tempo do EMPACOTADOR em periodos:', value=22)
            
            st.write("Tempo de preparo - BOLO:")
            col1, col2, col3 = st.beta_columns(3)
            with col1:
                tFORNOBOLO = st.number_input('BOLO/FORNO - Tempo:', help='Tempo de preparo em periodos' ,  value=1.00, format="%.2f")
            with col2:
                tPADEIROBOLO = st.number_input('BOLO/PADEIRO - Tempo:', help='Tempo de preparo em periodos:',  value=0.50, format="%.2f")
            with col3:
                tEMPACOTADORBOLO = st.number_input('BOLO/EMPACOTADOR - Tempo:', help='Tempo de preparo em periodos:',  value=1.00, format="%.2f")
            
            st.write("Tempo de preparo - TORTA:")
            col1, col2, col3 = st.beta_columns(3)
            with col1:
                tFORNOTORTA = st.number_input('TORTA/FORNO - Tempo:', help='Tempo de preparo em periodos' ,  value=0.50, format="%.2f")
            with col2:
                tPADEIROTORTA = st.number_input('TORTA/PADEIRO - Tempo:', help='Tempo de preparo em periodos:',  value=2.00, format="%.2f")
            with col3:
                tEMPACOTADORTORTA = st.number_input('TORTA/EMPACOTADOR - Tempo:', help='Tempo de preparo em periodos:',  value=0.50, format="%.2f")


        if st.button("Enviar"):
            model = ConcreteModel()
            ##### dual
            model.dual = Suffix(direction=Suffix.IMPORT)

            ## VARIAVEIS DE DECISAO: ---------------------------------
            BOLO  = model.BOLO = pyo.Var(within=PositiveReals)
            TORTA = model.TORTA = pyo.Var(within=PositiveReals)

            ## CONSTRAINTS: ---------------------------------
            model.FORNO =       pyo.Constraint(expr= tFORNOBOLO * BOLO + tFORNOTORTA * TORTA <= pFORNO)
            model.PADEIRO =     pyo.Constraint(expr= tPADEIROBOLO * BOLO + tPADEIROTORTA * TORTA <= pPADEIRO)
            model.EMPACOTADOR = pyo.Constraint(expr= tEMPACOTADORBOLO *BOLO + tEMPACOTADORTORTA * TORTA <= pEMPACOTADOR)
            model.minBOLO =     pyo.Constraint(expr= BOLO >= minBOLO)
            model.minTORTA =    pyo.Constraint(expr= TORTA >= minTORTA)

            model.obj = pyo.Objective(expr= LucroBOLO*BOLO +LucroTORTA*TORTA, sense=maximize)
            model.pprint()
            
            solver = SolverFactory('glpk')
            results = solver.solve(model, tee=True)
            st.write("A solução encontrada é: ", results.solver.termination_condition)
            with st.beta_expander(" DUAL:"):
                st.write("Capacidade semelhantes que daram o mesmo resulado:")
                for c in [model.FORNO, model.PADEIRO, model.EMPACOTADOR]:
                    st.write(c, c(), c.lslack(), c.uslack(), model.dual[c])

            # print(results)
            st.write("Para obter o maior lucro a sugestão de fábricação é:")
            st.write("BOLO:",pyo.value(BOLO),"TORTA é:",pyo.value(TORTA) )
            st.write("LUCRO esperado será:", pyo.value(model.obj))
            with st.beta_expander("Explicação:"):
                st.write( '(', LucroBOLO,' X ', pyo.value(BOLO) , ") + (" , LucroTORTA,' X ',pyo.value(TORTA) ,' = ', pyo.value(model.obj),')')


#### MIX DE PRODUÇÃO - ELABORADO:
    elif choice == "II - Linha de Produção Elaborada":
        st.subheader("Linha de Produção Elaborada") 
        with st.beta_expander("Objetivo:"):
            st.markdown("Minimizar o custo de produção incluindo o valor do frete, que é um valor fixo por capacidade maxima por pacote. \n \n \
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
            st_dias = st.number_input('Periodo:', help='Periodo para atingir a demanda. Em dias, por exemplo' , value=30)
        with col2:
             st_containers = st.number_input('Itens por pacote(frete):', help='Quantidade maxima de itens por pacote(frete):',value=2.50, format="%.2f")
        
        # embed streamlit docs in a streamlit app
        import streamlit.components.v1 as components
        components.iframe(st.secrets["private_gsheets_url"],width=1500, height=800)
        
        if st.button("Enviar"):
            with st.spinner('Processando...'):
                ## cria o dataframe com o resultado da sugestao:
                df,vOF =  roda_algoritmo(st_containers, st_dias)
                st.success('Feito!')
            
            st.write("Custo total para fabricação da Demanda - aba Resultado:", locale.currency(vOF,grouping=True))
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
        st.subheader("Carteira de Investimentos... em contrução.")    






#### SOBRE:    
    elif choice == "SOBRE":
        col1, col2, col3, col4= st.beta_columns(4)
        with col1:
            with st.beta_expander("Fonte"):
                st.write(
                        """
                        Livros: 
                        - Pyomo Documentation - Release 5.7.1.dev0  - Aug 17, 2020 
                        - Pesquisa Operacional para Cursos de Engenharia - Patrícia Belfiore & Luiz Paulo Fávero 
                        - ...
                        """  )
       
        st.info("Desenvolvido por Paulo Cristiano Klein, com ajuda de muitos amigos!\n"
                "Mantido por [Paulo Klein](https://www.linkedin.com/in/pauloklein/). "
                "Me visite também em https://github.com/Tianoklein")
        if st.button("OBRIGADO!!!"):
            st.balloons()
        html_temp = '''<a href="mailto:tianoklein@hotmail.com?subject=Streamlit DO/PO Parse&body=Tenho uma sugestão: ">  Duvidas, criticas e sugestões </a>'''
        import streamlit.components.v1 as components
        components.html(html_temp)


if __name__ == '__main__':
    main()