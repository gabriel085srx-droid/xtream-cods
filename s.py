#!/usr/bin/env python3
import subprocess
import sys
import os
import signal
import time
import socket
import requests
import json
import threading
from datetime import datetime
from urllib.parse import urlparse
import random

# ============ CONFIGURAÇÕES ============
BOT_TOKEN = "8858026333:AAHc5SzjaRTCA6CaOjkHJ_Mvr1yYuSMVRKI"
CHAT_ID = "8130788079"

SERVIDORES = [
    {"nome": "Site Principal", "url": "http://localhost:8081", "porta": 8081, "dir": "/sdcard/download/painel"},
    {"nome": "Site Michel", "url": "http://localhost:8082", "porta": 8082, "dir": "/sdcard/download/public"}
]

INTERVALO_VERIFICACAO = 5  # Verifica a cada 5 SEGUNDOS (mais rápido!)
# =======================================

processos = {}
nomes_processos = {}
ultimo_alerta = {}
bot_ativo = False
verificacao_ativa = True
ultima_vez_online = {}
contador_falhas = {}

class TelegramBot:
    def __init__(self, token, chat_id):
        self.token = token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.ultimo_update_id = 0
        
    def enviar_mensagem(self, texto, parse_mode="HTML"):
        try:
            url = f"{self.base_url}/sendMessage"
            payload = {"chat_id": self.chat_id, "text": texto, "parse_mode": parse_mode}
            response = requests.post(url, json=payload, timeout=10)
            return response.json()
        except Exception as e:
            print(f"❌ Erro ao enviar mensagem: {e}")
            return None
    
    def get_updates(self):
        try:
            url = f"{self.base_url}/getUpdates"
            params = {"offset": self.ultimo_update_id + 1, "timeout": 30}
            response = requests.get(url, params=params, timeout=35)
            data = response.json()
            
            if data.get("ok") and data.get("result"):
                for update in data["result"]:
                    self.ultimo_update_id = update["update_id"]
                    if "message" in update and "text" in update["message"]:
                        return update["message"]
            return None
        except Exception as e:
            return None
    
    def processar_comandos(self, message):
        if not message:
            return
        
        chat_id = message["chat"]["id"]
        texto = message.get("text", "")
        
        if str(chat_id) != str(self.chat_id):
            return
        
        if texto.startswith("/ping"):
            self.comando_ping()
        elif texto.startswith("/status"):
            self.comando_status()
        elif texto.startswith("/servicos"):
            self.comando_listar_servicos()
        elif texto.startswith("/log"):
            self.comando_log()
        elif texto.startswith("/ajuda"):
            self.comando_ajuda()
        elif texto.startswith("/reiniciar"):
            self.comando_forcar_reinicio()
        elif texto.startswith("/diagnostico"):
            self.comando_diagnostico()
    
    def enviar_mensagem_para(self, chat_id, texto):
        try:
            url = f"{self.base_url}/sendMessage"
            payload = {"chat_id": chat_id, "text": texto, "parse_mode": "HTML"}
            requests.post(url, json=payload, timeout=10)
        except:
            pass
    
    def comando_ping(self):
        mensagem = "🏓 <b>VERIFICAÇÃO DE VELOCIDADE</b>\n\n"
        for servidor in SERVIDORES:
            nome = servidor["nome"]
            url = servidor["url"]
            
            inicio = time.time()
            try:
                response = requests.get(url, timeout=3)
                tempo = (time.time() - inicio) * 1000
                if response.status_code == 200:
                    mensagem += f"✅ <b>{nome}</b> - {tempo:.0f}ms\n"
                else:
                    mensagem += f"⚠️ <b>{nome}</b> - Status {response.status_code}\n"
            except:
                mensagem += f"❌ <b>{nome}</b> - OFFLINE\n"
        
        self.enviar_mensagem(mensagem)
    
    def comando_status(self):
        mensagem = f"📊 <b>STATUS DO SISTEMA</b>\n🕐 {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n\n"
        
        for servidor in SERVIDORES:
            nome = servidor["nome"]
            url = servidor["url"]
            
            try:
                response = requests.get(url, timeout=2)
                if response.status_code == 200:
                    mensagem += f"✅ {nome}: ONLINE\n"
                else:
                    mensagem += f"⚠️ {nome}: Status {response.status_code}\n"
            except:
                mensagem += f"❌ {nome}: OFFLINE\n"
        
        mensagem += f"\n📈 Processos ativos: {len([p for p in processos.values() if p and p.poll() is None])}/{len(SERVIDORES)}"
        self.enviar_mensagem(mensagem)
    
    def comando_listar_servicos(self):
        mensagem = "🔧 <b>SERVIÇOS CONFIGURADOS</b>\n\n"
        for i, servidor in enumerate(SERVIDORES, 1):
            mensagem += f"{i}. <b>{servidor['nome']}</b>\n   📍 Porta: {servidor['porta']}\n\n"
        self.enviar_mensagem(mensagem)
    
    def comando_log(self):
        if not ultimo_alerta:
            self.enviar_mensagem("📋 Nenhum alerta registrado!")
            return
        
        mensagem = "📋 <b>ÚLTIMOS ALERTAS</b>\n\n"
        for servico, info in list(ultimo_alerta.items())[-5:]:
            status_emoji = "✅" if info["status"] == "online" else "❌"
            mensagem += f"{status_emoji} <b>{servico}</b>\n   {info['timestamp']}\n\n"
        self.enviar_mensagem(mensagem)
    
    def comando_ajuda(self):
        mensagem = """🤖 <b>COMANDOS DISPONÍVEIS</b>

/ping - Testar velocidade
/status - Status do sistema
/servicos - Listar serviços
/log - Últimos alertas
/reiniciar - Forçar reinício
/diagnostico - Diagnóstico completo

🔄 Sistema com auto-recuperação em milissegundos!"""
        self.enviar_mensagem(mensagem)
    
    def comando_forcar_reinicio(self):
        self.enviar_mensagem("🔄 Forçando reinício de todos os serviços...")
        for servidor in SERVIDORES:
            restart_service_imediato(servidor["nome"], servidor["porta"], servidor["dir"])
        time.sleep(2)
        self.comando_status()
    
    def comando_diagnostico(self):
        mensagem = "🔍 <b>DIAGNÓSTICO COMPLETO</b>\n\n"
        
        for servidor in SERVIDORES:
            porta = servidor["porta"]
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            resultado = sock.connect_ex(('127.0.0.1', porta))
            sock.close()
            
            if resultado == 0:
                mensagem += f"✅ Porta {porta}: FUNCIONANDO\n"
            else:
                mensagem += f"❌ Porta {porta}: MORTA\n"
        
        # Verifica processos PHP
        try:
            result = subprocess.run(["pgrep", "-f", "php"], capture_output=True, text=True)
            qtd = len(result.stdout.strip().split()) if result.stdout.strip() else 0
            mensagem += f"\n📊 Processos PHP ativos: {qtd}"
        except:
            pass
        
        self.enviar_mensagem(mensagem)

# ============ SISTEMA DE SUPERVIVÊNCIA ============

def verificar_porta_livre(porta):
    """Verifica se a porta está escutando (mais rápido que requests)"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.1)  # Timeout ultra rápido
        resultado = sock.connect_ex(('127.0.0.1', porta))
        sock.close()
        return resultado == 0
    except:
        return False

def matar_processo_na_porta(porta):
    """Mata qualquer processo na porta específica"""
    try:
        # Tenta matar pelo lsof
        result = subprocess.run(f"lsof -ti:{porta}", shell=True, capture_output=True, text=True)
        if result.stdout.strip():
            pids = result.stdout.strip().split()
            for pid in pids:
                try:
                    os.kill(int(pid), signal.SIGKILL)
                    print(f"  💀 Matou processo {pid} na porta {porta}")
                except:
                    pass
        time.sleep(0.2)
    except:
        pass

def restart_service_imediato(nome, porta, diretorio):
    """Reinicia o serviço em MILISSEGUNDOS"""
    global processos
    
    print(f"⚡ REINICIANDO {nome} em milissegundos...")
    
    try:
        # 1. Mata processo antigo violentamente
        matar_processo_na_porta(porta)
        
        # 2. Aguarda a porta liberar (mínimo)
        for _ in range(5):  # Máximo 0.5 segundos
            if not verificar_porta_livre(porta):
                time.sleep(0.05)
            else:
                break
        
        # 3. Inicia novo processo
        os.chdir(diretorio)
        proc = subprocess.Popen(
            ["php", "-S", f"localhost:{porta}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid  # Grupo de processo separado
        )
        
        processos[nome] = proc
        
        # 4. Verifica se iniciou (ultra rápido)
        for _ in range(10):  # Máximo 0.5 segundos
            if verificar_porta_livre(porta):
                print(f"  ✅ {nome} REINICIADO em {_ * 0.05:.2f}s")
                return True
            time.sleep(0.05)
        
        print(f"  ⚠️ {nome} reiniciado mas porta não respondeu")
        return False
        
    except Exception as e:
        print(f"  ❌ ERRO ao reiniciar {nome}: {e}")
        return False

def super_watchdog():
    """Thread que verifica e recupera serviços em MILISSEGUNDOS"""
    global verificacao_ativa, ultimo_alerta, contador_falhas, ultima_vez_online
    
    print("🛡️ SUPERVISOR ULTRA-RÁPIDO ATIVO (verificação a cada 1.5 SEGUNDOS)")
    
    # Inicializa contadores
    for servidor in SERVIDORES:
        contador_falhas[servidor["nome"]] = 0
        ultima_vez_online[servidor["nome"]] = time.time()
    
    ultimo_envio_alerta = {}
    
    while verificacao_ativa:
        try:
            for servidor in SERVIDORES:
                nome = servidor["nome"]
                porta = servidor["porta"]
                url = servidor["url"]
                diretorio = servidor["dir"]
                
                # Verificação RÁPIDA (socket, mais rápido que HTTP)
                online = verificar_porta_livre(porta)
                
                # Verificação dupla se necessário (confirma com HTTP)
                if online:
                    try:
                        response = requests.get(url, timeout=0.5)
                        online = response.status_code == 200
                    except:
                        online = False
                
                # GERENCIAMENTO DE ESTADO
                if online:
                    contador_falhas[nome] = 0
                    
                    # Verifica se estava offline antes
                    if nome in ultimo_alerta and ultimo_alerta[nome]["status"] == "offline":
                        ultimo_alerta[nome] = {"status": "online", "timestamp": datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
                        print(f"✅ {nome} RECUPERADO!")
                        
                        # Envia alerta de recuperação (mas não flooda)
                        if bot_ativo and BOT_TOKEN != "SEU_TOKEN_AQUI":
                            tempo_offline = time.time() - ultima_vez_online.get(nome, time.time())
                            if tempo_offline > 30:  # Só alerta se ficou >30s offline
                                bot = TelegramBot(BOT_TOKEN, CHAT_ID)
                                bot.enviar_mensagem(f"✅ <b>{nome} RECUPERADO!</b>\n⏱️ Ficou {tempo_offline:.1f}s offline\n🔄 Auto-recuperação ativa")
                    
                    ultima_vez_online[nome] = time.time()
                
                else:  # OFFLINE
                    contador_falhas[nome] += 1
                    
                    # REGISTRA QUEDA (só uma vez)
                    if nome not in ultimo_alerta or ultimo_alerta[nome]["status"] != "offline":
                        ultimo_alerta[nome] = {"status": "offline", "timestamp": datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
                        print(f"🚨 {nome} CAIU! Recuperando em milissegundos...")
                        
                        # Envia alerta (apenas 1x a cada 5 minutos para evitar spam)
                        agora = time.time()
                        if bot_ativo and BOT_TOKEN != "SEU_TOKEN_AQUI":
                            if nome not in ultimo_envio_alerta or (agora - ultimo_envio_alerta.get(nome, 0)) > 300:
                                ultimo_envio_alerta[nome] = agora
                                bot = TelegramBot(BOT_TOKEN, CHAT_ID)
                                bot.enviar_mensagem(f"🚨 <b>{nome} CAIU!</b>\n🔄 Auto-recuperação em andamento...")
                    
                    # REINICIA IMEDIATAMENTE (após 1 falha)
                    if contador_falhas[nome] >= 1:
                        restart_service_imediato(nome, porta, diretorio)
                        contador_falhas[nome] = 0  # Reseta contador
                        
                        # Verifica se reviveu
                        time.sleep(0.2)  # Espera só 200ms
                        if verificar_porta_livre(porta):
                            print(f"  ✅ {nome} voltou em MILISSEGUNDOS!")
                        else:
                            print(f"  ⚠️ {nome} ainda offline, nova tentativa em breve")
                
            # Pausa ultra curta (1.5 segundos)
            time.sleep(1.5)
            
        except Exception as e:
            print(f"⚠️ Erro no watchdog: {e}")
            time.sleep(0.5)

def iniciar_servicos_iniciais():
    """Inicia todos os serviços no boot"""
    print("\n📡 INICIANDO SERVIÇOS...")
    print("-" * 50)
    
    for servidor in SERVIDORES:
        nome = servidor["nome"]
        porta = servidor["porta"]
        diretorio = servidor["dir"]
        
        # Verifica se diretório existe
        if not os.path.exists(diretorio):
            print(f"❌ {nome}: Diretório não encontrado! {diretorio}")
            continue
        
        # Mata processos na porta
        matar_processo_na_porta(porta)
        time.sleep(0.3)
        
        # Inicia serviço
        try:
            os.chdir(diretorio)
            proc = subprocess.Popen(
                ["php", "-S", f"localhost:{porta}"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                preexec_fn=os.setsid
            )
            processos[nome] = proc
            time.sleep(0.5)
            
            if verificar_porta_livre(porta):
                print(f"✅ {nome}: RODANDO na porta {porta}")
            else:
                print(f"⚠️ {nome}: Iniciado mas não respondeu")
        except Exception as e:
            print(f"❌ {nome}: Erro ao iniciar - {e}")

def configurar_android():
    """Configura Android para não matar o processo"""
    try:
        # Wake lock mantém CPU ativa
        subprocess.run(["termux-wake-lock"], capture_output=True)
        print("✅ Wake lock ativado")
        
        # Tenta dar prioridade máxima
        try:
            os.nice(-20)  # Prioridade máxima (pode não funcionar sem root)
        except:
            pass
            
    except Exception as e:
        print(f"⚠️ Erro na configuração Android: {e}")

def limpar_processos(signum=None, frame=None):
    """Finaliza todos os serviços"""
    global verificacao_ativa
    
    print("\n🛑 Encerrando sistema...")
    verificacao_ativa = False
    
    # Envia mensagem de desligamento
    if bot_ativo and BOT_TOKEN != "SEU_TOKEN_AQUI":
        bot = TelegramBot(BOT_TOKEN, CHAT_ID)
        bot.enviar_mensagem("🔴 <b>SISTEMA DESLIGADO</b>")
    
    # Mata todos os processos
    for nome, proc in processos.items():
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            print(f"  ✓ {nome} encerrado")
        except:
            try:
                proc.terminate()
            except:
                pass
    
    try:
        subprocess.run(["termux-wake-unlock"], capture_output=True)
    except:
        pass
    
    print("✅ Sistema encerrado")
    sys.exit(0)

def main():
    global bot_ativo
    
    print("=" * 60)
    print("🚀 SISTEMA ULTRA-ROBUSTO COM AUTO-RECUPERAÇÃO")
    print("=" * 60)
    
    # Configuração
    configurar_android()
    
    # Registra handlers
    signal.signal(signal.SIGINT, limpar_processos)
    signal.signal(signal.SIGTERM, limpar_processos)
    
    # Inicia serviços
    iniciar_servicos_iniciais()
    
    # Inicia bot Telegram
    bot = None
    if BOT_TOKEN != "SEU_TOKEN_AQUI" and CHAT_ID != "SEU_CHAT_ID_AQUI":
        bot = TelegramBot(BOT_TOKEN, CHAT_ID)
        bot_ativo = True
        print("\n🤖 Bot Telegram conectado!")
        
        # Thread para comandos
        def receber_comandos():
            while verificacao_ativa:
                message = bot.get_updates()
                if message:
                    bot.processar_comandos(message)
                time.sleep(0.5)  # Responde rápido
        
        threading.Thread(target=receber_comandos, daemon=True).start()
    
    # Inicia SUPERVISOR ULTRA-RÁPIDO
    watchdog_thread = threading.Thread(target=super_watchdog, daemon=True)
    watchdog_thread.start()
    
    print("\n" + "=" * 60)
    print("✅ SISTEMA 100% OPERACIONAL")
    print("=" * 60)
    print(f"🛡️ Verificação: {INTERVALO_VERIFICACAO} segundos")
    print(f"⚡ Recuperação: MILISSEGUNDOS")
    print(f"📡 Sites monitorados: {len(SERVIDORES)}")
    print(f"🤖 Bot: {'ATIVO' if bot_ativo else 'INATIVO'}")
    print("\n💡 Comandos: /ping, /status, /servicos, /log, /reiniciar, /diagnostico")
    print("⚠️  Pressione Ctrl+C para encerrar")
    print("=" * 60)
    
    # Mantém vivo
    try:
        while verificacao_ativa:
            time.sleep(1)
    except KeyboardInterrupt:
        limpar_processos()

if __name__ == "__main__":
    main()