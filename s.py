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
from concurrent.futures import ThreadPoolExecutor
import psutil
import random

# ============ CONFIGURAÇÕES ============
BOT_TOKEN = "8858026333:AAHc5SzjaRTCA6CaOjkHJ_Mvr1yYuSMVRKI"
CHAT_ID = "8130788079"

# Configurações dos serviços
SERVIDORES = [
    {"nome": "Site Principal", "url": "http://localhost:8081", "porta": 8081, "dir": "/sdcard/download/painel"},
    {"nome": "Site Michel", "url": "http://localhost:8082", "porta": 8082, "dir": "/sdcard/download/public"}
]

# Intervalo de verificação (segundos)
INTERVALO_VERIFICACAO = 10  # Reduzido para 10 segundos
INTERVALO_RECONEXAO = 2  # Tenta reconectar a cada 2 segundos
TEMPO_MAXIMO_OFFLINE = 30  # Tempo máximo offline antes de alerta crítico
# =======================================

processos = {}
nomes_processos = {}
ultimo_alerta = {}
bot_ativo = False
verificacao_ativa = True
executor = ThreadPoolExecutor(max_workers=10)
fila_reconexao = []

class TelegramBot:
    def __init__(self, token, chat_id):
        self.token = token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.ultimo_update_id = 0
        
    def enviar_mensagem(self, texto, parse_mode="HTML"):
        """Envia mensagem para o Telegram"""
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
            print(f"❌ Erro ao enviar mensagem: {e}")
            return None
    
    def get_updates(self):
        """Busca novas mensagens do bot"""
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
        except Exception as e:
            return None
    
    def processar_comandos(self, message):
        """Processa comandos recebidos"""
        if not message:
            return
        
        chat_id = message["chat"]["id"]
        texto = message.get("text", "")
        user = message["from"]["first_name"]
        
        if str(chat_id) != str(self.chat_id):
            self.enviar_mensagem_para(chat_id, "⛔ Acesso não autorizado!")
            return
        
        if texto.startswith("/ping"):
            self.comando_ping()
        elif texto.startswith("/status"):
            self.comando_status()
        elif texto.startswith("/servicos"):
            self.comando_listar_servicos()
        elif texto.startswith("/log"):
            self.comando_log()
        elif texto.startswith("/ajuda") or texto.startswith("/help"):
            self.comando_ajuda()
        elif texto.startswith("/speed"):
            self.comando_speedtest()
        elif texto.startswith("/parar"):
            self.comando_parar()
        elif texto.startswith("/reiniciar"):
            self.comando_reiniciar_sistema()
        elif texto.startswith("/forcar_reconexao"):
            self.comando_forcar_reconexao()
        elif texto.startswith("/processos"):
            self.comando_listar_processos()
    
    def enviar_mensagem_para(self, chat_id, texto):
        """Envia mensagem para um chat específico"""
        try:
            url = f"{self.base_url}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": texto,
                "parse_mode": "HTML"
            }
            requests.post(url, json=payload, timeout=10)
        except:
            pass
    
    def comando_parar(self):
        """Comando /parar - Para todo o sistema"""
        global verificacao_ativa
        mensagem = "🛑 <b>DESLIGANDO SISTEMA...</b>\n\n"
        mensagem += f"🕐 {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n"
        mensagem += "⚠️ Todos os serviços serão encerrados!"
        self.enviar_mensagem(mensagem)
        
        # Para o sistema após enviar a mensagem
        threading.Thread(target=lambda: (time.sleep(1), limpar_processos()), daemon=True).start()
    
    def comando_reiniciar_sistema(self):
        """Comando /reiniciar - Reinicia todo o sistema"""
        mensagem = "🔄 <b>REINICIANDO SISTEMA...</b>\n\n"
        mensagem += "✅ Todos os serviços serão reiniciados!"
        self.enviar_mensagem(mensagem)
        
        threading.Thread(target=reiniciar_todos_servicos, daemon=True).start()
    
    def comando_forcar_reconexao(self):
        """Comando /forcar_reconexao - Força reconexão de todos serviços"""
        mensagem = "🔄 <b>FORÇANDO RECONEXÃO DE TODOS SERVIÇOS</b>\n\n"
        mensagem += "⏳ Tentando reconectar todos os serviços..."
        self.enviar_mensagem(mensagem)
        
        threading.Thread(target=forcar_reconexao_todos, daemon=True).start()
    
    def comando_listar_processos(self):
        """Comando /processos - Lista todos os processos ativos"""
        mensagem = "📊 <b>PROCESSOS ATIVOS</b>\n\n"
        
        for nome, proc in processos.items():
            if proc and proc.poll() is None:
                mensagem += f"✅ {nome}: PID {proc.pid}\n"
            else:
                mensagem += f"❌ {nome}: INATIVO\n"
        
        mensagem += f"\n📈 Total de processos ativos: {sum(1 for p in processos.values() if p and p.poll() is None)}"
        self.enviar_mensagem(mensagem)
    
    def comando_ping(self):
        """Comando /ping - Verifica velocidade dos sites"""
        mensagem = "🏓 <b>VERIFICAÇÃO DE VELOCIDADE</b>\n\n"
        
        for servidor in SERVIDORES:
            nome = servidor["nome"]
            url = servidor["url"]
            porta = servidor["porta"]
            
            inicio = time.time()
            try:
                response = requests.get(url, timeout=5)
                tempo = (time.time() - inicio) * 1000
                
                if response.status_code == 200:
                    tamanho = len(response.content)
                    mensagem += f"✅ <b>{nome}</b>\n"
                    mensagem += f"   ⚡ Resposta: {tempo:.0f}ms\n"
                    mensagem += f"   📦 Tamanho: {tamanho} bytes\n\n"
                else:
                    mensagem += f"⚠️ <b>{nome}</b>\n"
                    mensagem += f"   Status HTTP: {response.status_code}\n\n"
            except requests.exceptions.Timeout:
                mensagem += f"❌ <b>{nome}</b>\n"
                mensagem += f"   ⏰ Timeout (5s)\n\n"
            except requests.exceptions.ConnectionError:
                mensagem += f"❌ <b>{nome}</b>\n"
                mensagem += f"   🔌 Conexão recusada\n\n"
            except Exception as e:
                mensagem += f"❌ <b>{nome}</b>\n"
                mensagem += f"   Erro: {str(e)[:100]}\n\n"
        
        try:
            inicio = time.time()
            response = requests.get("https://www.google.com", timeout=5)
            tempo_internet = (time.time() - inicio) * 1000
            mensagem += f"🌐 <b>Internet Geral</b>\n"
            mensagem += f"   ⚡ Google: {tempo_internet:.0f}ms\n"
            mensagem += f"   📡 Conectividade: OK"
        except:
            mensagem += f"🌐 <b>Internet Geral</b>\n"
            mensagem += f"   ❌ SEM CONEXÃO COM INTERNET!"
        
        self.enviar_mensagem(mensagem)
    
    def comando_status(self):
        """Comando /status - Status detalhado"""
        mensagem = "📊 <b>STATUS DO SISTEMA</b>\n\n"
        mensagem += f"🕐 {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n\n"
        
        for servidor in SERVIDORES:
            nome = servidor["nome"]
            url = servidor["url"]
            proc = processos.get(nome)
            
            if proc and proc.poll() is None:
                try:
                    response = requests.get(url, timeout=3)
                    if response.status_code == 200:
                        mensagem += f"✅ {nome}: ONLINE (PID {proc.pid})\n"
                    else:
                        mensagem += f"⚠️ {nome}: ERRO HTTP {response.status_code}\n"
                except:
                    mensagem += f"⚠️ {nome}: ONLINE MAS NÃO RESPONDE\n"
            else:
                mensagem += f"❌ {nome}: OFFLINE\n"
        
        cloudflare_status = verificar_cloudflare()
        mensagem += f"\n{'✅' if cloudflare_status else '❌'} Cloudflare Tunnel: "
        mensagem += f"{'ATIVO' if cloudflare_status else 'INATIVO'}\n"
        
        mensagem += f"✅ WakeLock: ATIVO\n"
        
        processos_ativos = sum(1 for p in processos.values() if p and p.poll() is None)
        mensagem += f"\n📈 Processos ativos: {processos_ativos}/{len(processos)}\n"
        mensagem += f"🔍 Monitoramento: ATIVO (intervalo: {INTERVALO_VERIFICACAO}s)"
        
        self.enviar_mensagem(mensagem)
    
    def comando_listar_servicos(self):
        """Comando /servicos - Lista serviços"""
        mensagem = "🔧 <b>SERVIÇOS CONFIGURADOS</b>\n\n"
        
        for i, servidor in enumerate(SERVIDORES, 1):
            mensagem += f"{i}. <b>{servidor['nome']}</b>\n"
            mensagem += f"   📍 URL: {servidor['url']}\n"
            mensagem += f"   🔌 Porta: {servidor['porta']}\n"
            mensagem += f"   📁 Dir: {servidor['dir']}\n\n"
        
        mensagem += "💡 Comandos disponíveis:\n"
        mensagem += "/ping - Testar velocidade\n"
        mensagem += "/status - Status completo\n"
        mensagem += "/parar - Parar sistema\n"
        mensagem += "/reiniciar - Reiniciar sistema\n"
        mensagem += "/forcar_reconexao - Forçar reconexão"
        
        self.enviar_mensagem(mensagem)
    
    def comando_log(self):
        """Comando /log - Últimos alertas"""
        if not ultimo_alerta:
            self.enviar_mensagem("📋 Nenhum alerta registrado ainda!")
            return
        
        mensagem = "📋 <b>ÚLTIMOS ALERTAS</b>\n\n"
        for servico, info in ultimo_alerta.items():
            status_emoji = "✅" if info["status"] == "online" else "❌"
            mensagem += f"{status_emoji} <b>{servico}</b>\n"
            mensagem += f"   Status: {info['status']}\n"
            mensagem += f"   Última mudança: {info['timestamp']}\n"
            mensagem += f"   Reconexões: {info.get('reconexoes', 0)}x\n\n"
        
        self.enviar_mensagem(mensagem)
    
    def comando_ajuda(self):
        """Comando /ajuda - Lista comandos"""
        mensagem = """🤖 <b>COMANDOS DISPONÍVEIS</b>

📊 <b>Informação:</b>
/ping - Testar velocidade dos sites
/status - Status completo do sistema
/servicos - Listar serviços configurados
/log - Últimos alertas do sistema
/processos - Listar processos ativos
/speed - Testar velocidade da internet

🛠️ <b>Controle:</b>
/parar - Para todo o sistema
/reiniciar - Reinicia todos os serviços
/forcar_reconexao - Força reconexão imediata

ℹ️ <b>Outros:</b>
/ajuda - Mostrar esta mensagem

🚨 <b>Alertas automáticos:</b>
• Serviços offline/online
• Quedas de internet
• Falhas no Cloudflare
• Reconexão automática em ms"""
        
        self.enviar_mensagem(mensagem)
    
    def comando_speedtest(self):
        """Comando /speed - Teste de velocidade"""
        self.enviar_mensagem("⏳ Iniciando teste de velocidade...")
        
        mensagem = "🚀 <b>TESTE DE VELOCIDADE</b>\n\n"
        
        try:
            inicio = time.time()
            response = requests.get("https://speed.cloudflare.com/__down?bytes=5000000", timeout=30)
            tempo = time.time() - inicio
            tamanho_mb = len(response.content) / (1024 * 1024)
            velocidade = tamanho_mb / tempo
            mensagem += f"📥 <b>Download:</b> {velocidade:.1f} MB/s\n"
        except:
            mensagem += f"📥 <b>Download:</b> ❌ Falhou\n"
        
        try:
            latencias = []
            for _ in range(3):
                inicio = time.time()
                requests.get("https://www.google.com", timeout=5)
                latencias.append((time.time() - inicio) * 1000)
            
            latencia_media = sum(latencias) / len(latencias)
            mensagem += f"📡 <b>Latência:</b> {latencia_media:.0f}ms\n"
            mensagem += f"📊 <b>Min/Max:</b> {min(latencias):.0f}/{max(latencias):.0f}ms"
        except:
            mensagem += f"📡 <b>Latência:</b> ❌ Falhou"
        
        self.enviar_mensagem(mensagem)

def verificar_cloudflare():
    """Verifica se o túnel Cloudflare está rodando"""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "cloudflared"],
            capture_output=True,
            text=True
        )
        return bool(result.stdout.strip())
    except:
        return False

def iniciar_servico_php(nome, diretorio, porta):
    """Inicia um serviço PHP e retorna o processo"""
    try:
        if not os.path.exists(diretorio):
            print(f"✗ Diretório {diretorio} não encontrado!")
            return None
        
        os.chdir(diretorio)
        
        # Mata processos antigos na porta
        subprocess.run(f"fuser -k {porta}/tcp", shell=True, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        time.sleep(0.5)
        
        proc = subprocess.Popen(
            ["php", "-S", f"localhost:{porta}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Aguarda o serviço iniciar
        time.sleep(1)
        
        # Verifica se o serviço está respondendo
        for _ in range(5):
            try:
                response = requests.get(f"http://localhost:{porta}", timeout=2)
                if response.status_code == 200:
                    print(f"✓ {nome} iniciado em localhost:{porta}")
                    return proc
            except:
                time.sleep(0.5)
        
        print(f"⚠️ {nome} iniciado mas não responde ainda")
        return proc
    except Exception as e:
        print(f"✗ Erro ao iniciar {nome}: {e}")
        return None

def iniciar_cloudflared():
    """Inicia o túnel Cloudflare"""
    try:
        # Mata processos antigos do cloudflared
        subprocess.run(["pkill", "-f", "cloudflared"], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        time.sleep(0.5)
        
        proc = subprocess.Popen(
            ["cloudflared", "tunnel", "run", "meutunel"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        print("✓ Cloudflared tunnel iniciado")
        return proc
    except Exception as e:
        print(f"✗ Erro no cloudflared: {e}")
        return None

def iniciar_termux_wakelock():
    """Mantém o Termux ativo"""
    try:
        subprocess.run(
            ["termux-wake-lock"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False
        )
        print("✓ termux-wake-lock ativado")
        return True
    except Exception as e:
        print(f"✗ Erro no termux-wake-lock: {e}")
        return False

def reconectar_servico(nome_servico, bot=None, forcar=False):
    """Reconecta um serviço específico rapidamente"""
    global ultimo_alerta
    
    if nome_servico not in [s["nome"] for s in SERVIDORES]:
        return False
    
    servidor = next(s for s in SERVIDORES if s["nome"] == nome_servico)
    
    # Marca como reconectando
    if nome_servico not in ultimo_alerta:
        ultimo_alerta[nome_servico] = {"status": "offline", "timestamp": datetime.now().strftime('%d/%m/%Y %H:%M:%S'), "reconexoes": 0}
    
    ultimo_alerta[nome_servico]["reconexoes"] = ultimo_alerta[nome_servico].get("reconexoes", 0) + 1
    
    print(f"🔄 Tentando reconectar {nome_servico}... (tentativa {ultimo_alerta[nome_servico]['reconexoes']})")
    
    # Tenta reconectar
    novo_proc = iniciar_servico_php(nome_servico, servidor["dir"], servidor["porta"])
    
    if novo_proc:
        processos[nome_servico] = novo_proc
        
        # Envia alerta de reconexão
        if bot:
            bot.enviar_mensagem(
                f"🔄 <b>{nome_servico} RECONECTADO!</b>\n"
                f"⚡ Reconexão bem-sucedida\n"
                f"📊 Tentativas: {ultimo_alerta[nome_servico]['reconexoes']}\n"
                f"🕐 {datetime.now().strftime('%H:%M:%S')}"
            )
        
        ultimo_alerta[nome_servico]["status"] = "online"
        ultimo_alerta[nome_servico]["timestamp"] = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        return True
    
    return False

def monitor_auto_reconexao(bot):
    """Thread que monitora e reconecta serviços automaticamente"""
    global verificacao_ativa
    
    ultimo_status = {}
    tempo_offline = {}
    
    for servidor in SERVIDORES:
        ultimo_status[servidor["nome"]] = True
        tempo_offline[servidor["nome"]] = 0
    
    while verificacao_ativa:
        for servidor in SERVIDORES:
            nome = servidor["nome"]
            url = servidor["url"]
            proc = processos.get(nome)
            
            # Verifica se o processo está vivo
            if not proc or proc.poll() is not None:
                if ultimo_status[nome]:
                    print(f"❌ {nome} caiu! Tentando reconectar...")
                    ultimo_status[nome] = False
                    tempo_offline[nome] = 0
                    
                    # Alerta de queda
                    if bot:
                        bot.enviar_mensagem(
                            f"🚨 <b>{nome} CAIU!</b>\n"
                            f"🔄 Iniciando reconexão automática...\n"
                            f"🕐 {datetime.now().strftime('%H:%M:%S')}"
                        )
                
                # Tenta reconectar imediatamente
                reconectar_servico(nome, bot)
                tempo_offline[nome] += INTERVALO_RECONEXAO
                
                # Alerta crítico se ficou muito tempo offline
                if tempo_offline[nome] >= TEMPO_MAXIMO_OFFLINE and bot:
                    bot.enviar_mensagem(
                        f"⚠️ <b>CRÍTICO: {nome} OFFLINE HÁ {TEMPO_MAXIMO_OFFLINE}s</b>\n"
                        f"📊 Tentativas: {ultimo_alerta.get(nome, {}).get('reconexoes', 0)}\n"
                        f"🔄 Verificando conexão de rede..."
                    )
            else:
                # Processo está vivo, verifica se responde
                try:
                    response = requests.get(url, timeout=2)
                    if response.status_code == 200:
                        if not ultimo_status[nome]:
                            # Voltou ao ar
                            print(f"✅ {nome} restaurado!")
                            ultimo_status[nome] = True
                            tempo_offline[nome] = 0
                            
                            if bot:
                                bot.enviar_mensagem(
                                    f"✅ <b>{nome} RESTAURADO!</b>\n"
                                    f"⚡ Serviço normalizado\n"
                                    f"🕐 {datetime.now().strftime('%H:%M:%S')}"
                                )
                    else:
                        # Processo vivo mas não responde
                        if ultimo_status[nome]:
                            print(f"⚠️ {nome} não responde (HTTP {response.status_code})")
                            # Mata e reinicia
                            if proc:
                                proc.terminate()
                                time.sleep(0.5)
                            reconectar_servico(nome, bot)
                except:
                    # Não responde, mata e reinicia
                    if ultimo_status[nome]:
                        print(f"⚠️ {nome} não responde, reiniciando...")
                        if proc:
                            proc.terminate()
                            time.sleep(0.5)
                        reconectar_servico(nome, bot)
        
        # Verifica Cloudflare
        if not verificar_cloudflare():
            print("⚠️ Cloudflare Tunnel caiu, reiniciando...")
            cloud_proc = iniciar_cloudflared()
            if cloud_proc:
                processos["Cloudflare"] = cloud_proc
                if bot:
                    bot.enviar_mensagem("🔄 Cloudflare Tunnel reiniciado!")
        
        time.sleep(INTERVALO_RECONEXAO)

def forcar_reconexao_todos():
    """Força reconexão de todos os serviços"""
    for servidor in SERVIDORES:
        nome = servidor["nome"]
        print(f"🔄 Forçando reconexão de {nome}...")
        reconectar_servico(nome, bot, forcar=True)
        time.sleep(0.5)
    
    if bot:
        bot.enviar_mensagem("✅ Todos os serviços foram reiniciados!")

def reiniciar_todos_servicos():
    """Reinicia todos os serviços do zero"""
    global processos
    
    print("🔄 Reiniciando todos os serviços...")
    
    # Mata todos os processos
    for nome, proc in processos.items():
        if proc:
            try:
                proc.terminate()
                time.sleep(0.3)
            except:
                pass
    
    time.sleep(1)
    processos = {}
    
    # Reinicia serviços
    iniciar_cloudflared()
    time.sleep(0.5)
    
    for servidor in SERVIDORES:
        proc = iniciar_servico_php(servidor["nome"], servidor["dir"], servidor["porta"])
        if proc:
            processos[servidor["nome"]] = proc
        time.sleep(0.3)
    
    if bot:
        bot.enviar_mensagem(
            "✅ <b>SISTEMA REINICIADO COM SUCESSO!</b>\n"
            f"🕐 {datetime.now().strftime('%H:%M:%S')}\n"
            "🔄 Todos os serviços foram reiniciados"
        )

def limpar_processos(signum=None, frame=None):
    """Finaliza todos os processos"""
    global verificacao_ativa, bot_ativo
    
    print("\n🛑 Encerrando todos os serviços...")
    verificacao_ativa = False
    
    if bot_ativo and BOT_TOKEN != "SEU_TOKEN_AQUI":
        bot_temp = TelegramBot(BOT_TOKEN, CHAT_ID)
        bot_temp.enviar_mensagem(
            "🔴 <b>SISTEMA DESLIGADO</b>\n"
            f"🕐 {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n"
            "👋 Sistema encerrado via comando /parar"
        )
    
    for nome, proc in processos.items():
        try:
            if proc:
                proc.terminate()
                proc.wait(timeout=2)
                print(f"  ✓ {nome} encerrado")
        except:
            try:
                if proc:
                    proc.kill()
            except:
                pass
    
    try:
        subprocess.run(["pkill", "-f", "cloudflared"])
        subprocess.run(["termux-wake-unlock"])
        print("✓ Limpeza concluída")
    except:
        pass
    
    print("✅ Todos os serviços foram encerrados")
    sys.exit(0)

def main():
    global bot_ativo, bot
    
    print("=" * 70)
    print("🚀 INICIANDO SISTEMA ULTRA RESILIENTE COM AUTO-RECUPERAÇÃO")
    print("=" * 70)
    print()
    
    signal.signal(signal.SIGINT, limpar_processos)
    signal.signal(signal.SIGTERM, limpar_processos)
    
    print("📡 Iniciando serviços...")
    print("-" * 50)
    
    iniciar_termux_wakelock()
    time.sleep(0.5)
    
    # Inicia Cloudflare
    cloud_proc = iniciar_cloudflared()
    if cloud_proc:
        processos["Cloudflare"] = cloud_proc
    time.sleep(0.5)
    
    # Inicia serviços PHP
    for servidor in SERVIDORES:
        proc = iniciar_servico_php(servidor["nome"], servidor["dir"], servidor["porta"])
        if proc:
            processos[servidor["nome"]] = proc
        time.sleep(0.5)
    
    print("-" * 50)
    print()
    
    # Inicia bot
    bot = None
    if BOT_TOKEN != "SEU_TOKEN_AQUI" and CHAT_ID != "SEU_CHAT_ID_AQUI":
        bot = TelegramBot(BOT_TOKEN, CHAT_ID)
        bot_ativo = True
        print("🤖 Bot Telegram conectado!")
        
        def receber_comandos():
            while verificacao_ativa:
                message = bot.get_updates()
                if message:
                    bot.processar_comandos(message)
                time.sleep(1)
        
        thread_comandos = threading.Thread(target=receber_comandos, daemon=True)
        thread_comandos.start()
    
    # Inicia monitoramento de reconexão
    thread_monitor = threading.Thread(
        target=monitor_auto_reconexao,
        args=(bot,),
        daemon=True
    )
    thread_monitor.start()
    
    print("\n" + "=" * 70)
    print("✅ SISTEMA INICIADO COM SUCESSO!")
    print("=" * 70)
    print(f"  📡 Wake Lock: ✅ Ativo")
    print(f"  ☁️  Cloudflare: {'✅' if processos.get('Cloudflare') else '❌'}")
    
    for servidor in SERVIDORES:
        proc = processos.get(servidor["nome"])
        print(f"  🌐 {servidor['nome']}: {'✅' if proc and proc.poll() is None else '❌'} http://localhost:{servidor['porta']}")
    
    print(f"  🤖 Bot Telegram: {'✅ Conectado' if bot_ativo else '❌'}")
    print(f"  🔄 Auto-recuperação: ✅ Ativa (a cada {INTERVALO_RECONEXAO}s)")
    print(f"  🔍 Monitoramento: ✅ Ativo")
    print()
    print("💡 Comandos disponíveis no Telegram:")
    print("   /ping, /status, /servicos, /log, /parar, /reiniciar, /forcar_reconexao")
    print()
    print("⚠️  Sistema com auto-recuperação ativa!")
    print("   - Reconexão automática em milissegundos")
    print("   - Monitoramento de processos")
    print("   - Reinício automático de serviços")
    print()
    print("=" * 70)
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        limpar_processos()

if __name__ == "__main__":
    bot = None
    main()