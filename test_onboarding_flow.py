#!/usr/bin/env python3
"""
Script de teste para verificar o fluxo de onboarding com dados coletados.
Testa se todos os 8 campos são coletados antes de chamar store_employee_data.
"""

import asyncio
import json
from app.services.ai_orchestrator import AiOrchestrator
from app.services.queue_manager import QueueManager
from app.configs.config import config

async def test_onboarding_flow():
    print("\n" + "="*80)
    print("🧪 TESTE: Fluxo de Onboarding com Coleta Automática")
    print("="*80)
    
    queue_manager = QueueManager()
    session_id = "test-session-001"
    chat_key = f"chat:{session_id}"
    phone = "5581999999999"
    
    # Criar orchestrator
    print(f"\n1️⃣ Criando AiOrchestrator para {chat_key}...")
    orchestrator = AiOrchestrator(
        session_id=session_id,
        chat_key=chat_key,
        user_type="funcionario",
        openai_api_key=config.OpenAIConstants.OPENAI_API_KEY,
        queue_manager=queue_manager,
        phone=phone
    )
    
    # Preparar agentes
    print("2️⃣ Preparando agentes e GraphFlow...")
    await orchestrator.prepare()
    print(f"   ✅ Agentes criados: {list(orchestrator.agents.keys())}")
    print(f"   ✅ collected_data: {orchestrator.collected_data}")
    
    # Simular primeira mensagem
    print("\n3️⃣ Enviando primeira mensagem (Nome)...")
    first_msg = "João Silva"
    async for msg in orchestrator.execute(first_message=first_msg, employee_name="test-user"):
        print(f"   📨 Resposta: {msg[:80]}...")
    
    print(f"   ✅ collected_data após 1ª exec: {orchestrator.collected_data}")
    print(f"   ✅ Coleta completa? {orchestrator._is_collection_complete()}")
    
    # Simular segunda mensagem
    print("\n4️⃣ Enviando segunda mensagem (CPF)...")
    second_msg = "12345678901"
    async for msg in orchestrator.execute(first_message=second_msg, employee_name="test-user"):
        print(f"   📨 Resposta: {msg[:80]}...")
    
    print(f"   ✅ collected_data após 2ª exec: {orchestrator.collected_data}")
    print(f"   ✅ Coleta completa? {orchestrator._is_collection_complete()}")
    
    # Simular mensagem com múltiplos dados
    print("\n5️⃣ Enviando mensagem com MÚLTIPLOS dados (3 campos)...")
    multi_msg = "01/01/1990 | Desenvolvedor | joao@email.com"
    async for msg in orchestrator.execute(first_message=multi_msg, employee_name="test-user"):
        print(f"   📨 Resposta: {msg[:80]}...")
    
    print(f"   ✅ collected_data após 3ª exec: {orchestrator.collected_data}")
    print(f"   ✅ Coleta completa? {orchestrator._is_collection_complete()}")
    
    # Limpar Redis
    await queue_manager.close()
    
    print("\n" + "="*80)
    print("✅ Teste completado!")
    print("="*80 + "\n")

if __name__ == "__main__":
    asyncio.run(test_onboarding_flow())
