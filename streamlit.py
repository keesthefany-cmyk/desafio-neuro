import streamlit as st
import requests
import json
from datetime import datetime

# ================================================================================
# CONFIGURAÇÃO STREAMLIT
# ================================================================================

st.set_page_config(
    page_title="🤖 NEUROTECH Onboarding",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ================================================================================
# ESTILOS CUSTOMIZADOS
# ================================================================================

st.markdown("""
<style>
    body {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    }
    
    .stChatMessage {
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 1rem;
    }
    
    h1 {
        color: #667eea;
        text-align: center;
        margin-bottom: 2rem;
        font-size: 2rem;
    }
    
    .stButton > button {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        border-radius: 0.5rem;
        padding: 0.5rem 1.5rem;
        font-weight: bold;
        transition: all 0.3s ease;
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 12px rgba(102, 126, 234, 0.4);
    }
    
    .stSelectbox > div > div > select {
        border-radius: 0.5rem;
        border: 2px solid #667eea;
    }
</style>
""", unsafe_allow_html=True)

# ================================================================================
# INICIALIZAR SESSION STATE
# ================================================================================

if "messages" not in st.session_state:
    st.session_state.messages = []

if "user_type" not in st.session_state:
    st.session_state.user_type = "funcionario"

if "session_id" not in st.session_state:
    st.session_state.session_id = f"session-{datetime.now().strftime('%Y%m%d%H%M%S')}"

if "phone" not in st.session_state:
    st.session_state.phone = "5581999999999"

if "api_url" not in st.session_state:
    st.session_state.api_url = "http://localhost:7000"

if "employee_name" not in st.session_state:
    st.session_state.employee_name = ""

# ================================================================================
# HEADER
# ================================================================================

col1, col2, col3 = st.columns([1, 2, 1])

with col2:
    st.markdown("# 🧠 NEUROTECH Onboarding")

# ================================================================================
# SELETOR DE TIPO DE USUÁRIO (SIDEBAR)
# ================================================================================

with st.sidebar:
    st.markdown("### ⚙️ Configuração")
    st.session_state.user_type = st.selectbox(
        "👤 Tipo de Usuário",
        ["funcionario", "rh"],
        index=0 if st.session_state.user_type == "funcionario" else 1
    )
    
    st.divider()
    
    if st.button("🗑️ Limpar Chat", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

# ================================================================================
# CHAT
# ================================================================================

st.markdown(f"**Conectado como:** `{st.session_state.user_type.upper()}`")
st.divider()

# Exibir histórico de mensagens
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Input e envio (CORRIGIDO)
user_input = st.chat_input("Digite sua mensagem...")

if user_input:
    # Adicionar mensagem do usuário
    st.session_state.messages.append({
        "role": "user",
        "content": user_input
    })
    
    with st.chat_message("user"):
        st.markdown(user_input)
    
    # Enviar para API
    with st.spinner("🔄 Processando..."):
        try:
            payload = {
                "msg": user_input,
                "phone": st.session_state.phone,
                "rid": st.session_state.session_id,
                "employee_name": st.session_state.employee_name
            }
            
            # Adicionar user_type como parâmetro (ou header)
            headers = {
                "X-User-Type": st.session_state.user_type
            }
            
            response = requests.post(
                f"{st.session_state.api_url}/api/onboarding/message",
                json=payload,
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                assistant_response = data.get("response", ["Erro ao processar resposta"])[0]
                
                # Adicionar resposta do assistente
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": assistant_response
                })
                
                with st.chat_message("assistant"):
                    st.markdown(assistant_response)
                
                st.rerun()
            else:
                st.error(f"❌ Erro: {response.status_code}")
                st.error(response.text)
        
        except requests.exceptions.ConnectionError:
            st.error("❌ Erro de conexão com a API. Verifique se o servidor está rodando.")
        except Exception as e:
            st.error(f"❌ Erro: {str(e)}")

# ================================================================================
# FOOTER
# ================================================================================

st.divider()
st.markdown("""
<div style="text-align: center; color: #666; font-size: 0.85rem;">
    <p>🧠 NEUROTECH - Sistema de Onboarding Inteligente</p>
    <p>Powered by AutoGen + OpenAI + Elasticsearch</p>
</div>
""", unsafe_allow_html=True)