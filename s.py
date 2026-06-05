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
# COLOQUE AQUI SEU TOKEN DO BOT E SEU CHAT ID
BOT_TOKEN = "8858026333:AAHc5SzjaRTCA6CaOjkHJ_Mvr1yYuSMVRKI"  # Ex: "123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
CHAT_ID = "8130788079"  # Ex: "123456789"

# Configurações dos serviços
SERVIDORES = [
    {"nome": "Site Principal", "url": "http://localhost:8081", "porta": 8081, "comando_iniciar": "python3 -m http.server 8081"},
    {"nome": "Site Michel", "url": "http://localhost:8082", "porta": 8082, "comando_iniciar": "python3 -m http.server 8082"}
]

# Intervalo de verificação normal (segundos)
INTERVALO_VERIFICACAO = 10  # Verifica a cada 10 segundos
# Intervalo de reconexão rápida (milissegundos)
RECONEXAO_RAPIDA_INTERVALO_MS = 500 # Tenta reconectar a cada 500ms

# =======================================

processos = []
nomes_processos = {}
ultimo_alerta = {}
bot_ativo = False
verificacao_ativa = True

# Lock para acesso seguro a variaveis globais (processos, nomes_processos)
process_lock = threading.Lock()

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
        global verificacao_ativa
        if not message:
            return
        
        chat_id = message["chat"]["id"]
        texto = message.get("text", "")
        user = message["from"]["first_name"]
        
        # Só responde se for o chat autorizado
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
        
        elif texto.startswith("/reiniciar"):
            args = texto.split()
            if len(args) > 1:
                self.comando_reiniciar_servico(args[1])
            else:
                self.enviar_mensagem("❌ Use: /reiniciar <nome_do_serviço>")
        
        elif texto.startswith("/parar"):
            self.enviar_mensagem("🛑 Recebido comando /parar. Encerrando todos os serviços e o monitoramento...")
            verificacao_ativa = False # Sinaliza para as threads pararem
            limpar_processos(None, None) # Chama a função de limpeza
            
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
                    mensagem += f"   📦 Tamanho: {tamanho} bytes\n"
                    mensagem += f"   🔗 URL: {url}\n\n"
                else:
                    mensagem += f"⚠️ <b>{nome}</b>\n"
                    mensagem += f"   Status HTTP: {response.status_code}\n\n"
            except requests.exceptions.Timeout:
                mensagem += f"❌ <b>{nome}</b>\n"
                mensagem += f"   ⏰ Timeout (5s) - Servidor não respondeu\n"
                mensagem += f"   🔌 Porta {porta} pode estar fechada\n\n"
            except requests.exceptions.ConnectionError:
                mensagem += f"❌ <b>{nome}</b>\n"
                mensagem += f"   🔌 Conexão recusada - Servidor offline\n"
                mensagem += f"   🚫 Porta {porta} não está ouvindo\n\n"
            except Exception as e:
                mensagem += f"❌ <b>{nome}</b>\n"
                mensagem += f"   Erro: {str(e)[:100]}\n\n"
        
        # Verifica internet geral
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
        mensagem += f"🕐 {datetime.now().strftime("%d/%m/%Y %H:%M:%S")}\n\n"
        
        # Status dos serviços
        for servidor in SERVIDORES:
            nome = servidor["nome"]
            url = servidor["url"]
            
            try:
                response = requests.get(url, timeout=5)
                if response.status_code == 200:
                    mensagem += f"✅ {nome}: ONLINE\n"
                else:
                    mensagem += f"⚠️ {nome}: Status {response.status_code}\n"
            except:
                mensagem += f"❌ {nome}: OFFLINE\n"
        
        # Status do Cloudflare
        cloudflare_status = verificar_cloudflare()
        mensagem += f"\n{'✅' if cloudflare_status else '❌'} Cloudflare Tunnel: "
        mensagem += f"{'ATIVO' if cloudflare_status else 'INATIVO'}\n"
        
        # Status do WakeLock
        mensagem += f"✅ WakeLock: ATIVO\n"
        
        # Verifica processos
        with process_lock:
            processos_ativos = sum(1 for p in processos if p.poll() is None)
            mensagem += f"\n📈 Processos ativos: {processos_ativos}/{len(processos)}"
        
        self.enviar_mensagem(mensagem)
    
    def comando_listar_servicos(self):
        """Comando /servicos - Lista serviços"""
        mensagem = "🔧 <b>SERVIÇOS CONFIGURADOS</b>\n\n"
        
        for i, servidor in enumerate(SERVIDORES, 1):
            mensagem += f"{i}. <b>{servidor['nome']}</b>\n"
            mensagem += f"   📍 URL: {servidor['url']}\n"
            mensagem += f"   🔌 Porta: {servidor['porta']}\n\n"
        
        mensagem += "💡 Use /ping para testar velocidade\n"
        mensagem += "💡 Use /status para verificar status"
        
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
            mensagem += f"   Última mudança: {info['timestamp']}\n\n"
        
        self.enviar_mensagem(mensagem)
    
    def comando_ajuda(self):
        """Comando /ajuda - Lista comandos"""
        mensagem = """🤖 <b>COMANDOS DISPONÍVEIS</b>

/ping - Testar velocidade dos sites
/status - Status completo do sistema
/servicos - Listar serviços configurados
/log - Últimos alertas do sistema
/speed - Testar velocidade da internet
/reiniciar <nome_do_serviço> - Reinicia um serviço específico
/parar - Encerrar todos os serviços e o monitoramento
/ajuda - Mostrar esta mensagem

🚨 <b>Alertas automáticos:</b>
• Serviços offline/online
• Quedas de internet
• Falhas no Cloudflare
• Erros críticos do sistema"""
        
        self.enviar_mensagem(mensagem)
    
    def comando_speedtest(self):
        """Comando /speed - Teste de velocidade simples"""
        self.enviar_mensagem("⏳ Iniciando teste de velocidade... (pode levar 30s)")
        
        mensagem = "🚀 <b>TESTE DE VELOCIDADE</b>\n\n"
        
        # Teste de download
        try:
            inicio = time.time()
            response = requests.get("https://speed.cloudflare.com/__down?bytes=5000000", timeout=30)
            tempo = time.time() - inicio
            tamanho_mb = len(response.content) / (1024 * 1024)
            velocidade = tamanho_mb / tempo
            mensagem += f"📥 <b>Download:</b> {velocidade:.1f} MB/s\n"
        except:
            mensagem += f"📥 <b>Download:</b> ❌ Falhou\n"
        
        # Teste de latência
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
    
    def comando_reiniciar_servico(self, nome_servico):
        """Comando /reiniciar - Reinicia um serviço específico"""
        self.enviar_mensagem(f"⏳ Reiniciando {nome_servico}...")
        
        with process_lock:
            if nome_servico in nomes_processos:
                processo_info = nomes_processos[nome_servico]
                processo = processo_info["processo"]
                comando = processo_info["comando"]
                
                if processo.poll() is None: # Se o processo ainda estiver rodando
                    print(f"Encerrando processo existente para {nome_servico}...")
                    processo.terminate()
                    processo.wait(timeout=5)
                
                print(f"Iniciando {nome_servico} novamente com o comando: {comando}")
                novo_processo = subprocess.Popen(comando, shell=True, preexec_fn=os.setsid, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                processo_info["processo"] = novo_processo
                self.enviar_mensagem(f"✅ {nome_servico} reiniciado com sucesso!")
            else:
                self.enviar_mensagem(f"❌ Serviço '{nome_servico}' não encontrado para reiniciar.")
        
        time.sleep(2)
        self.comando_status()

def iniciar_processo(nome, comando):
    """Inicia um processo e o adiciona à lista global"""
    global processos, nomes_processos
    try:
        # Usamos os.setsid para criar um novo grupo de processo, o que ajuda a garantir que o processo filho
        # não seja encerrado quando o processo pai receber um SIGINT (Ctrl+C), a menos que o pai o encerre explicitamente.
        processo = subprocess.Popen(comando, shell=True, preexec_fn=os.setsid, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with process_lock:
            processos.append(processo)
            nomes_processos[nome] = {"processo": processo, "comando": comando}
        print(f"✅ Processo '{nome}' iniciado com PID: {processo.pid}")
        return True
    except Exception as e:
        print(f"❌ Erro ao iniciar processo '{nome}': {e}")
        return False

def iniciar_termux_wakelock():
    return iniciar_processo("Termux WakeLock", "termux-wake-lock")

def iniciar_cloudflared():
    return iniciar_processo("Cloudflared Tunnel", "cloudflared tunnel run --url http://localhost:8080") # Exemplo, ajuste a porta se necessário

def iniciar_site_principal():
    # Pega o comando de iniciar do SERVIDORES
    comando = next((s["comando_iniciar"] for s in SERVIDORES if s["nome"] == "Site Principal"), None)
    if comando:
        return iniciar_processo("Site Principal", comando)
    return False

def iniciar_site_michel():
    # Pega o comando de iniciar do SERVIDORES
    comando = next((s["comando_iniciar"] for s in SERVIDORES if s["nome"] == "Site Michel" ), None)
    if comando:
        return iniciar_processo("Site Michel", comando)
    return False

def verificar_cloudflare():
    """Verifica se o túnel Cloudflare está rodando"""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "cloudflared"],
            capture_output=True,
            text=True,
            check=False # Não levanta exceção para código de saída diferente de zero
        )
        return bool(result.stdout.strip())
    except:
        return False

def limpar_processos(signum, frame):
    """Encerra todos os processos filhos iniciados e o wakelock"""
    global verificacao_ativa
    print("\n🛑 Sinal de encerramento recebido. Encerrando processos...")
    verificacao_ativa = False # Garante que as threads de monitoramento parem
    
    with process_lock:
        for nome, info in nomes_processos.items():
            p = info["processo"]
            if p.poll() is None:  # Se o processo ainda estiver rodando
                print(f"Encerrando {nome} (PID: {p.pid})...")
                try:
                    # Envia SIGTERM para o processo
                    os.killpg(os.getpgid(p.pid), signal.SIGTERM)
                    p.wait(timeout=5) # Espera o processo terminar
                except ProcessLookupError:
                    print(f"Processo {nome} (PID: {p.pid}) já encerrado.")
                except subprocess.TimeoutExpired:
                    print(f"Processo {nome} (PID: {p.pid}) não respondeu, forçando encerramento.")
                    os.killpg(os.getpgid(p.pid), signal.SIGKILL)
                    p.wait()
                except Exception as e:
                    print(f"Erro ao encerrar {nome}: {e}")
            else:
                print(f"Processo {nome} (PID: {p.pid}) já estava encerrado.")
        processos.clear()
        nomes_processos.clear()

    try:
        subprocess.run(["termux-wake-unlock"], 
                      stdout=subprocess.DEVNULL, 
                      stderr=subprocess.DEVNULL,
                      check=False)
        print("✓ Wakelock liberado")
    except:
        pass
    
    print("✅ Todos os serviços foram encerrados")
    sys.exit(0)

def monitorar_servicos(bot):
    """Thread de monitoramento contínuo com reconexão rápida"""
    global ultimo_alerta, verificacao_ativa
    
    print("\n👀 Monitoramento iniciado! Verificando a cada", INTERVALO_VERIFICACAO, "segundos...")
    print("=" * 50)
    
    # Estado inicial
    estados_anteriores = {}
    for servidor in SERVIDORES:
        estados_anteriores[servidor["nome"]] = None
    cloudflare_anterior = None
    
    # Envia mensagem de inicialização
    if bot:
        bot.enviar_mensagem(
            "🟢 <b>SISTEMA INICIADO</b>\n\n"
            f"🕐 {datetime.now().strftime("%d/%m/%Y %H:%M:%S")}\n"
            "📡 Monitoramento ativo\n"
            "🔔 Alertas configurados"
        )
    
    while verificacao_ativa:
        try:
            # Verifica cada servidor
            for servidor in SERVIDORES:
                nome = servidor["nome"]
                url = servidor["url"]
                comando_iniciar = servidor["comando_iniciar"]
                
                status_atual = "offline"
                try:
                    response = requests.get(url, timeout=5)
                    status_atual = "online" if response.status_code == 200 else "problema"
                except requests.exceptions.RequestException:
                    status_atual = "offline"
                
                # Se mudou o estado
                if estados_anteriores[nome] != status_atual:
                    estados_anteriores[nome] = status_atual
                    
                    if status_atual == "online":
                        mensagem = f"✅ <b>{nome} VOLTOU!</b>\n🕐 {datetime.now().strftime("%H:%M:%S")}\n🔗 {url}"
                    elif status_atual == "offline":
                        mensagem = f"🚨 <b>{nome} CAIU!</b>\n🕐 {datetime.now().strftime("%H:%M:%S")}\n🔗 {url}\n❌ Servidor não responde"
                        # Tenta reiniciar o serviço imediatamente
                        print(f"Tentando reiniciar o serviço '{nome}'...")
                        iniciar_processo(nome, comando_iniciar) # Tenta iniciar novamente
                        # Entra em modo de reconexão rápida
                        tentativas = 0
                        max_tentativas = int(INTERVALO_VERIFICACAO * 1000 / RECONEXAO_RAPIDA_INTERVALO_MS)
                        while verificacao_ativa and status_atual == "offline" and tentativas < max_tentativas:
                            time.sleep(RECONEXAO_RAPIDA_INTERVALO_MS / 1000)
                            try:
                                response = requests.get(url, timeout=2) # Timeout menor para reconexão rápida
                                status_atual = "online" if response.status_code == 200 else "problema"
                                if status_atual == "online":
                                    print(f"✅ {nome} voltou durante a reconexão rápida!")
                                    mensagem += f"\n✅ Reconectado em {tentativas * RECONEXAO_RAPIDA_INTERVALO_MS}ms"
                                    break
                            except requests.exceptions.RequestException:
                                status_atual = "offline"
                            tentativas += 1
                        if status_atual == "offline":
                            mensagem += f"\n❌ Não reconectado após {tentativas} tentativas."

                    else:
                        mensagem = f"⚠️ <b>{nome} COM PROBLEMA</b>\n🕐 {datetime.now().strftime("%H:%M:%S")}\n🔗 {url}"
                    
                    ultimo_alerta[nome] = {
                        "status": status_atual,
                        "timestamp": datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                    }
                    
                    print(f"{'✅' if status_atual == 'online' else '❌'} Alerta: {nome} - {status_atual}")
                    
                    if bot:
                        bot.enviar_mensagem(mensagem)
            
            # Verifica se o processo filho ainda está rodando
            with process_lock:
                if nome in nomes_processos:
                    p = nomes_processos[nome]["processo"]
                    if p.poll() is not None: # Se o processo terminou
                        print(f"⚠️ Processo '{nome}' (PID: {p.pid}) encerrou inesperadamente. Tentando reiniciar...")
                        iniciar_processo(nome, comando_iniciar) # Tenta reiniciar
                        if bot:
                            bot.enviar_mensagem(f"⚠️ <b>{nome}</b> encerrou inesperadamente e foi reiniciado.")

            
            # Verifica Cloudflare
            cf_status = verificar_cloudflare()
            if cloudflare_anterior != cf_status:
                cloudflare_anterior = cf_status
                
                if cf_status:
                    mensagem = "✅ <b>Cloudflare Tunnel RECONECTADO!</b>"
                else:
                    mensagem = "🚨 <b>Cloudflare Tunnel CAIU!</b>\n⚠️ Sites externos inacessíveis"
                
                if bot:
                    bot.enviar_mensagem(mensagem)
                print(mensagem)
            
            # Verifica internet geral a cada 5 verificações
            if int(time.time()) % (INTERVALO_VERIFICACAO * 5) < INTERVALO_VERIFICACAO:
                try:
                    requests.get("https://www.google.com", timeout=5)
                except:
                    if bot:
                        bot.enviar_mensagem(
                            "🌐 <b>ALERTA DE INTERNET</b>\n"
                            "❌ Sem conexão com a internet"
                        )
                    print("🌐 ALERTA: Sem conexão com a internet!")
            
            # Pequena pausa para não sobrecarregar a CPU
            time.sleep(0.1) # Pausa entre a verificação de cada serviço

        except Exception as e:
            print(f"❌ Erro crítico na thread de monitoramento: {e}")
            if bot:
                bot.enviar_mensagem(f"❌ Erro crítico no monitoramento: {e}")
        
        # Espera o intervalo de verificação, mas permite interrupção rápida
        for _ in range(int(INTERVALO_VERIFICACAO * 1000 / RECONEXAO_RAPIDA_INTERVALO_MS)):
            if not verificacao_ativa:
                break
            time.sleep(RECONEXAO_RAPIDA_INTERVALO_MS / 1000)

def main():
    global bot_ativo, verificacao_ativa
    
    print("=" * 60)
    print("🚀 INICIANDO SISTEMA COMPLETO COM MONITORAMENTO")
    print("=" * 60)
    print()
    
    # Verifica configurações do bot
    if BOT_TOKEN == "SEU_TOKEN_AQUI" or CHAT_ID == "SEU_CHAT_ID_AQUI":
        print("⚠️  AVISO: Configure o TOKEN e CHAT_ID do Telegram!")
        print("   Edite o script e adicione suas credenciais")
        print()
    
    # Registra handlers para Ctrl+C e SIGTERM
    signal.signal(signal.SIGINT, limpar_processos)
    signal.signal(signal.SIGTERM, limpar_processos)
    
    # Inicia serviços
    print("📡 Iniciando serviços...")
    print("-" * 50)
    
    wakelock_ok = iniciar_termux_wakelock()
    time.sleep(0.3)
    
    cloudflare_ok = iniciar_cloudflared()
    time.sleep(0.5)
    
    # Inicia os sites configurados dinamicamente
    for servidor in SERVIDORES:
        iniciar_processo(servidor["nome"], servidor["comando_iniciar"])
        time.sleep(0.3)
    
    print("-" * 50)
    print()
    
    # Inicia bot Telegram
    bot = None
    if BOT_TOKEN != "SEU_TOKEN_AQUI" and CHAT_ID != "SEU_CHAT_ID_AQUI":
        bot = TelegramBot(BOT_TOKEN, CHAT_ID)
        bot_ativo = True
        print("🤖 Bot Telegram conectado!")
        
        # Thread para receber comandos
        def receber_comandos_thread():
            while verificacao_ativa:
                try:
                    message = bot.get_updates()
                    if message:
                        bot.processar_comandos(message)
                except Exception as e:
                    print(f"❌ Erro na thread de comandos do bot: {e}")
                time.sleep(1) # Pequena pausa para evitar loop muito apertado
        
        thread_comandos = threading.Thread(target=receber_comandos_thread, daemon=True)
        thread_comandos.start()
    else:
        print("⚠️  Bot Telegram não configurado - monitoramento sem alertas")
    
    # Thread de monitoramento
    thread_monitor = threading.Thread(
        target=monitorar_servicos, 
        args=(bot,), 
        daemon=True
    )
    thread_monitor.start()
    
    # Status final
    print("\n" + "=" * 60)
    print("✅ SISTEMA INICIADO COM SUCESSO!")
    print("=" * 60)
    print(f"  Wake Lock: {'✅' if wakelock_ok else '❌'}")
    print(f"  Cloudflare: {'✅' if cloudflare_ok else '❌'}")
    for servidor in SERVIDORES:
        print(f"  {servidor['nome']}: {'✅ ' + servidor['url'] if servidor['nome'] in nomes_processos else '❌'}")
    print(f"  Bot Telegram: {'✅ Conectado' if bot_ativo else '❌ Não configurado'}")
    print(f"  Monitoramento: ✅ Ativo (normal a cada {INTERVALO_VERIFICACAO}s, reconexão rápida a cada {RECONEXAO_RAPIDA_INTERVALO_MS}ms)")
    print()
    print("💡 Comandos do bot: /ping, /status, /servicos, /log, /speed, /reiniciar <nome>, /parar")
    print("⚠️  Pressione Ctrl+C para encerrar tudo")
    print("=" * 60)
    
    # Mantém o script rodando
    try:
        while verificacao_ativa:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        limpar_processos(None, None) # Garante que a limpeza seja feita ao sair

if __name__ == "__main__":
    main()
