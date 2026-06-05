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

# ============ CONFIGURAÇÕES ============
BOT_TOKEN = "8858026333:AAHc5SzjaRTCA6CaOjkHJ_Mvr1yYuSMVRKI"
CHAT_ID = "8130788079"

# Configurações dos serviços
SERVIDORES = [
    {"nome": "Site Principal", "url": "http://localhost:8081", "porta": 8081, "dir": "/sdcard/download/painel"},
    {"nome": "Site Michel", "url": "http://localhost:8082", "porta": 8082, "dir": "/sdcard/download/public"}
]

# Intervalos (segundos)
INTERVALO_RECONEXAO = 3  # Tenta reconectar a cada 3 segundos
TEMPO_MAXIMO_OFFLINE = 30
# =======================================

processos = {}
nomes_processos = {}
ultimo_alerta = {}
bot_ativo = False
verificacao_ativa = True

class TelegramBot:
    def __init__(self, token, chat_id):
        self.token = token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.ultimo_update_id = 0
        
    def enviar_mensagem(self, texto, parse_mode="HTML"):
        try:
            url = f"{self.base_url}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": texto,
                "parse_mode": parse_mode
            }
            response = requests.post(url, json=payload, timeout=10)
            return response.json()
        except Exception as e:
            print(f"❌ Erro: {e}")
            return None
    
    def get_updates(self):
        try:
            url = f"{self.base_url}/getUpdates"
            params = {
                "offset": self.ultimo_update_id + 1,
                "timeout": 30
            }
            response = requests.get(url, params=params, timeout=35)
            data = response.json()
            
            if data.get("ok") and data.get("result"):
                for update in data["result"]:
                    self.ultimo_update_id = update["update_id"]
                    if "message" in update and "text" in update["message"]:
                        return update["message"]
            return None
        except:
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
        elif texto.startswith("/parar"):
            self.comando_parar()
        elif texto.startswith("/reiniciar"):
            self.comando_reiniciar()
        elif texto.startswith("/forcar"):
            self.comando_forcar()
    
    def comando_parar(self):
        """Para tudo imediatamente"""
        self.enviar_mensagem("🛑 DESLIGANDO SISTEMA...")
        threading.Thread(target=lambda: (time.sleep(1), limpar_processos()), daemon=True).start()
    
    def comando_reiniciar(self):
        """Reinicia todos serviços"""
        self.enviar_mensagem("🔄 REINICIANDO TODOS SERVIÇOS...")
        threading.Thread(target=reiniciar_tudo, daemon=True).start()
    
    def comando_forcar(self):
        """Força reconexão"""
        self.enviar_mensagem("🔄 FORÇANDO RECONEXÃO...")
        threading.Thread(target=forcar_reconexao_todos, daemon=True).start()
    
    def comando_ping(self):
        mensagem = "🏓 <b>VELOCIDADE</b>\n\n"
        
        for servidor in SERVIDORES:
            nome = servidor["nome"]
            url = servidor["url"]
            
            inicio = time.time()
            try:
                response = requests.get(url, timeout=3)
                tempo = (time.time() - inicio) * 1000
                if response.status_code == 200:
                    mensagem += f"✅ {nome}: {tempo:.0f}ms\n"
                else:
                    mensagem += f"⚠️ {nome}: HTTP {response.status_code}\n"
            except:
                mensagem += f"❌ {nome}: OFFLINE\n"
        
        self.enviar_mensagem(mensagem)
    
    def comando_status(self):
        mensagem = f"📊 STATUS - {datetime.now().strftime('%H:%M:%S')}\n\n"
        
        for servidor in SERVIDORES:
            nome = servidor["nome"]
            proc = processos.get(nome)
            
            if proc and proc.poll() is None:
                try:
                    requests.get(servidor["url"], timeout=2)
                    mensagem += f"✅ {nome}: ONLINE\n"
                except:
                    mensagem += f"⚠️ {nome}: PROCESSO VIVO\n"
            else:
                mensagem += f"❌ {nome}: OFFLINE\n"
        
        cf = verificar_cloudflare()
        mensagem += f"\n{'✅' if cf else '❌'} Cloudflare: {'ON' if cf else 'OFF'}"
        
        self.enviar_mensagem(mensagem)
    
    def comando_listar_servicos(self):
        mensagem = "🔧 SERVIÇOS\n\n"
        for i, s in enumerate(SERVIDORES, 1):
            mensagem += f"{i}. {s['nome']}\n   Porta: {s['porta']}\n\n"
        self.enviar_mensagem(mensagem)
    
    def comando_log(self):
        if not ultimo_alerta:
            self.enviar_mensagem("Sem alertas")
            return
        
        mensagem = "📋 ÚLTIMOS ALERTAS\n\n"
        for nome, info in list(ultimo_alerta.items())[-5:]:
            status = "✅" if info["status"] == "online" else "❌"
            mensagem += f"{status} {nome}\n   {info['timestamp']}\n   Tentativas: {info.get('tentativas',0)}\n\n"
        self.enviar_mensagem(mensagem)
    
    def comando_ajuda(self):
        mensagem = """🤖 COMANDOS:

/ping - Testar velocidade
/status - Status atual
/servicos - Listar serviços
/log - Ver alertas
/parar - Parar sistema
/reiniciar - Reiniciar
/forcar - Forçar reconexão

🔄 Auto-recuperação ativa!"""
        self.enviar_mensagem(mensagem)

def verificar_cloudflare():
    try:
        result = subprocess.run(["pgrep", "-f", "cloudflared"], capture_output=True, text=True)
        return bool(result.stdout.strip())
    except:
        return False

def matar_processo_porta(porta):
    """Mata processo que está usando uma porta"""
    try:
        subprocess.run(f"fuser -k {porta}/tcp", shell=True, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
    except:
        pass

def iniciar_servico(nome, diretorio, porta):
    """Inicia serviço PHP"""
    try:
        if not os.path.exists(diretorio):
            print(f"✗ Diretório não encontrado: {diretorio}")
            return None
        
        # Mata processo na porta
        matar_processo_porta(porta)
        time.sleep(0.3)
        
        os.chdir(diretorio)
        
        proc = subprocess.Popen(
            ["php", "-S", f"localhost:{porta}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        
        time.sleep(1)
        
        # Testa se subiu
        for _ in range(3):
            try:
                requests.get(f"http://localhost:{porta}", timeout=1)
                print(f"✓ {nome} iniciado na porta {porta}")
                return proc
            except:
                time.sleep(0.5)
        
        print(f"⚠️ {nome} iniciado mas não responde")
        return proc
    except Exception as e:
        print(f"✗ Erro {nome}: {e}")
        return None

def iniciar_cloudflared():
    try:
        subprocess.run(["pkill", "-f", "cloudflared"], stderr=subprocess.DEVNULL)
        time.sleep(0.5)
        
        proc = subprocess.Popen(
            ["cloudflared", "tunnel", "run", "meutunel"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        print("✓ Cloudflare iniciado")
        return proc
    except:
        print("✗ Cloudflare falhou")
        return None

def reconectar_servico(nome_servico, bot=None):
    """Reconecta um serviço específico"""
    servidor = None
    for s in SERVIDORES:
        if s["nome"] == nome_servico:
            servidor = s
            break
    
    if not servidor:
        return False
    
    print(f"🔄 Reconectando {nome_servico}...")
    
    # Registra tentativa
    if nome_servico not in ultimo_alerta:
        ultimo_alerta[nome_servico] = {"status": "offline", "timestamp": datetime.now().strftime('%H:%M:%S'), "tentativas": 0}
    
    ultimo_alerta[nome_servico]["tentativas"] += 1
    
    # Mata processo antigo
    if nome_servico in processos and processos[nome_servico]:
        try:
            processos[nome_servico].terminate()
            time.sleep(0.3)
        except:
            pass
    
    # Inicia novo
    novo_proc = iniciar_servico(nome_servico, servidor["dir"], servidor["porta"])
    
    if novo_proc:
        processos[nome_servico] = novo_proc
        ultimo_alerta[nome_servico]["status"] = "online"
        ultimo_alerta[nome_servico]["timestamp"] = datetime.now().strftime('%H:%M:%S')
        
        if bot:
            bot.enviar_mensagem(f"✅ {nome_servico} RECONECTADO! Tentativa #{ultimo_alerta[nome_servico]['tentativas']}")
        return True
    
    return False

def monitor_auto_reconexao(bot):
    """Monitora e reconecta automaticamente"""
    global verificacao_ativa
    
    status_servicos = {}
    for s in SERVIDORES:
        status_servicos[s["nome"]] = True
    
    while verificacao_ativa:
        # Verifica cada serviço
        for servidor in SERVIDORES:
            nome = servidor["nome"]
            url = servidor["url"]
            proc = processos.get(nome)
            
            # Verifica se processo está vivo
            if not proc or proc.poll() is not None:
                if status_servicos[nome]:
                    print(f"❌ {nome} CAIU!")
                    status_servicos[nome] = False
                    if bot:
                        bot.enviar_mensagem(f"🚨 {nome} CAIU! Reconectando...")
                
                # Reconecta imediatamente
                reconectar_servico(nome, bot)
            
            else:
                # Processo vivo, testa resposta
                try:
                    response = requests.get(url, timeout=2)
                    if response.status_code == 200:
                        if not status_servicos[nome]:
                            print(f"✅ {nome} VOLTOU!")
                            status_servicos[nome] = True
                            if bot:
                                bot.enviar_mensagem(f"✅ {nome} ONLINE NOVAMENTE!")
                    else:
                        # Não respondeu HTTP 200, reinicia
                        if status_servicos[nome]:
                            print(f"⚠️ {nome} erro HTTP {response.status_code}")
                            reconectar_servico(nome, bot)
                except:
                    # Não respondeu, reinicia
                    if status_servicos[nome]:
                        print(f"⚠️ {nome} sem resposta, reiniciando...")
                        reconectar_servico(nome, bot)
        
        # Verifica Cloudflare
        if not verificar_cloudflare():
            print("⚠️ Cloudflare caiu, reiniciando...")
            processos["Cloudflare"] = iniciar_cloudflared()
            if bot:
                bot.enviar_mensagem("🔄 Cloudflare reiniciado!")
        
        time.sleep(INTERVALO_RECONEXAO)

def forcar_reconexao_todos():
    """Força reconexão de todos serviços"""
    for servidor in SERVIDORES:
        reconectar_servico(servidor["nome"], bot)
        time.sleep(0.5)
    
    if bot:
        bot.enviar_mensagem("✅ TODOS SERVIÇOS RECONECTADOS!")

def reiniciar_tudo():
    """Reinicia sistema completo"""
    global processos
    
    if bot:
        bot.enviar_mensagem("🔄 Reiniciando todos serviços...")
    
    # Mata tudo
    for nome, proc in processos.items():
        if proc:
            try:
                proc.terminate()
            except:
                pass
    
    time.sleep(1)
    processos = {}
    
    # Inicia Cloudflare
    processos["Cloudflare"] = iniciar_cloudflared()
    time.sleep(0.5)
    
    # Inicia serviços
    for servidor in SERVIDORES:
        proc = iniciar_servico(servidor["nome"], servidor["dir"], servidor["porta"])
        if proc:
            processos[servidor["nome"]] = proc
        time.sleep(0.5)
    
    if bot:
        bot.enviar_mensagem("✅ SISTEMA REINICIADO COM SUCESSO!")

def iniciar_termux_wakelock():
    try:
        subprocess.run(["termux-wake-lock"], stderr=subprocess.DEVNULL)
        print("✓ WakeLock ativado")
        return True
    except:
        print("✗ WakeLock falhou")
        return False

def limpar_processos(signum=None, frame=None):
    global verificacao_ativa
    
    print("\n🛑 Encerrando...")
    verificacao_ativa = False
    
    if bot_ativo:
        temp_bot = TelegramBot(BOT_TOKEN, CHAT_ID)
        temp_bot.enviar_mensagem("🔴 SISTEMA DESLIGADO")
    
    for nome, proc in processos.items():
        if proc:
            try:
                proc.terminate()
                print(f"✓ {nome} encerrado")
            except:
                pass
    
    try:
        subprocess.run(["termux-wake-unlock"], stderr=subprocess.DEVNULL)
    except:
        pass
    
    print("✅ Sistema encerrado")
    sys.exit(0)

def main():
    global bot_ativo, bot, processos
    
    print("=" * 60)
    print("🚀 SISTEMA COM AUTO-RECUPERAÇÃO")
    print("=" * 60)
    
    signal.signal(signal.SIGINT, limpar_processos)
    signal.signal(signal.SIGTERM, limpar_processos)
    
    # WakeLock
    iniciar_termux_wakelock()
    
    # Inicia Cloudflare
    processos["Cloudflare"] = iniciar_cloudflared()
    time.sleep(0.5)
    
    # Inicia serviços
    for servidor in SERVIDORES:
        proc = iniciar_servico(servidor["nome"], servidor["dir"], servidor["porta"])
        if proc:
            processos[servidor["nome"]] = proc
        time.sleep(0.5)
    
    # Inicia bot
    bot = None
    if BOT_TOKEN and BOT_TOKEN != "SEU_TOKEN_AQUI":
        bot = TelegramBot(BOT_TOKEN, CHAT_ID)
        bot_ativo = True
        print("🤖 Bot conectado!")
        
        # Thread para comandos
        def comandos_thread():
            while verificacao_ativa:
                msg = bot.get_updates()
                if msg:
                    bot.processar_comandos(msg)
                time.sleep(1)
        
        threading.Thread(target=comandos_thread, daemon=True).start()
    
    # Thread de monitoramento
    threading.Thread(target=monitor_auto_reconexao, args=(bot,), daemon=True).start()
    
    print("\n✅ SISTEMA PRONTO!")
    print(f"🔄 Auto-recuperação: a cada {INTERVALO_RECONEXAO}s")
    print("📱 Comandos: /ping /status /servicos /log /parar /reiniciar /forcar")
    print("⚠️  Pressione Ctrl+C para sair\n")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        limpar_processos()

if __name__ == "__main__":
    bot = None
    main()