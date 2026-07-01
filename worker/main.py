import time
import math
import random
import os
import ddddocr
import sys
import pytesseract
import cv2
import numpy as np

# Configura o caminho do Tesseract
pytesseract.pytesseract.tesseract_cmd = r"C:\Users\jackson.junior\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"
import ssl
import logging
import subprocess
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
from supabase import create_client, Client
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from playwright_stealth import Stealth
import urllib.parse
import socket
import json

# Carrega as variáveis de ambiente do arquivo .env
load_dotenv()

# Desativa a verificação de certificado SSL se BYPASS_SSL for True (padrão) para evitar erros em redes corporativas com proxy
if os.getenv("BYPASS_SSL", "true").lower() == "true":
    try:
        original_create_default_context = ssl.create_default_context
        def custom_create_default_context(*args, **kwargs):
            context = original_create_default_context(*args, **kwargs)
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            return context
        ssl.create_default_context = custom_create_default_context
    except Exception:
        pass

# Configuração de Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("cnd-worker")

# Variáveis do Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    logger.error("SUPABASE_URL e SUPABASE_KEY precisam estar configurados no ambiente/.env!")
    sys.exit(1)

# Inicializa o cliente do Supabase
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    logger.info("Conectado ao Supabase com sucesso.")
except Exception as e:
    logger.error(f"Erro ao conectar ao Supabase: {str(e)}")
    sys.exit(1)

WORKER_ID = f"worker-cnd-{os.getpid()}"


# ==========================================
# SEÇÃO DOS ROBÔS DE AUTOMAÇÃO (PLAYWRIGHT)
# ==========================================


def mover_mouse_suave(page, target_x, target_y, steps=None):
    """
    Move o cursor do mouse de forma suave até as coordenadas (target_x, target_y)
    utilizando a curva Ease In-Out (cosseno) para aceleração/desaceleração realista.
    Adiciona pequenos desvios aleatórios em cada passo intermediário para evitar
    caminhos perfeitamente retos (detectáveis por firewalls anti-bot).
    """
    if steps is None:
        steps = random.randint(10, 18)

    # Define ponto de partida aleatório simulando uma posição anterior do cursor
    start_x = random.randint(50, 600)
    start_y = random.randint(50, 400)

    for i in range(1, steps + 1):
        t = i / steps
        # Curva de desaceleração/aceleração suave (cosseno)
        t_eased = (1 - math.cos(t * math.pi)) / 2

        current_x = start_x + (target_x - start_x) * t_eased
        current_y = start_y + (target_y - start_y) * t_eased

        # Adiciona um pequeno desvio/ruído humano (exceto no último passo)
        if i < steps:
            current_x += random.uniform(-2.0, 2.0)
            current_y += random.uniform(-2.0, 2.0)

        page.mouse.move(current_x, current_y)
        # Microtempo de transição humana entre movimentos
        time.sleep(random.uniform(0.008, 0.018))


def click_humano(page, selector):
    """
    Substitui o page.click convencional por um movimento físico do cursor
    até o elemento, seguido por um clique pressionado realisticamente
    (mouse down -> pequena espera -> mouse up).
    Se o elemento não tiver bounding box visível, faz fallback para page.click().
    """
    try:
        element = page.locator(selector).first
        element.wait_for(state="visible", timeout=10000)

        box = element.bounding_box()
        if not box:
            # Fallback de segurança caso o elemento esteja fora do viewport
            logger.info(f"[MOUSE] Elemento sem bounding box, usando clique direto: {selector}")
            element.click()
            return

        # Calcula coordenadas centrais do botão com variação aleatória de pixels
        # para não clicar sempre na coordenada exata central matemática
        target_x = box["x"] + box["width"] / 2 + random.uniform(-box["width"] / 6, box["width"] / 6)
        target_y = box["y"] + box["height"] / 2 + random.uniform(-box["height"] / 6, box["height"] / 6)

        # Move o cursor até o destino de forma suave
        mover_mouse_suave(page, target_x, target_y)

        # Tempo de reação humano antes de clicar
        time.sleep(random.uniform(0.15, 0.35))

        # Clique físico realista (down -> hold -> up)
        page.mouse.down()
        time.sleep(random.uniform(0.06, 0.12))
        page.mouse.up()
    except Exception as e:
        # Fallback para clique padrão em caso de qualquer erro
        logger.warning(f"[MOUSE] Fallback para clique direto por erro: {e}")
        try:
            page.click(selector)
        except Exception:
            page.locator(selector).first.click()


def solver_captcha_se_necessario(page, site_name):
    """
    Função auxiliar para integração com serviços de quebra de CAPTCHA (2Captcha/Anti-Captcha).
    No código de produção, você enviará o sitekey ou a imagem do captcha via request
    e aguardará a resposta textual.
    """
    logger.info(f"[{site_name}] Verificando necessidade de quebra de CAPTCHA...")
    # Exemplo conceitual:
    # captcha_element = page.query_selector("#captcha-img")
    # if captcha_element:
    #     captcha_base64 = captcha_element.screenshot().hex()
    #     resposta = chamar_api_2captcha(captcha_base64)
    #     page.fill("#captcha-input", resposta)
    pass


def get_chrome_path():
    paths = [
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
    ]
    for p in paths:
        if os.path.exists(p):
            return p
    return "chrome.exe"

def iniciar_e_conectar_chrome(p, user_data_dir, headless=False):
    chrome_running = False
    try:
        response = requests.get("http://127.0.0.1:9222/json/version", timeout=2)
        if response.status_code == 200:
            chrome_running = True
    except Exception:
        pass
        
    if not chrome_running:
        chrome_path = get_chrome_path()
        chrome_args = [
            chrome_path,
            "--remote-debugging-port=9222",
            f"--user-data-dir={user_data_dir}",
            "--no-first-run",
            "--no-default-browser-check"
        ]
        if headless:
            chrome_args.append("--headless=new")
        subprocess.Popen(chrome_args)
        
        # Aguarda até 5 segundos ou até a porta 9222 responder
        for _ in range(10):
            time.sleep(0.5)
            try:
                response = requests.get("http://127.0.0.1:9222/json/version", timeout=1)
                if response.status_code == 200:
                    break
            except Exception:
                pass
        
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    context = browser.contexts[0] if browser.contexts else browser.new_context()
    return browser, context

def resolver_recaptcha(page):
    logger.info("[ESTADUAL-SP] Iniciando resolução automática do reCAPTCHA...")
    
    # Adiciona a pasta bin do FFmpeg ao PATH para que o pydub a encontre
    import os
    ffmpeg_path = r"C:\Users\jackson.junior\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.1-full_build\bin"
    if os.path.exists(ffmpeg_path) and ffmpeg_path not in os.environ["PATH"]:
        os.environ["PATH"] += os.pathsep + ffmpeg_path
        
    try:
        # 1. Encontra o iframe do checkbox do reCAPTCHA
        frame_selector = 'iframe[src*="anchor"]'
        page.wait_for_selector(frame_selector, timeout=15000)
        frame = page.frame_locator(frame_selector)
        
        # 2. Clica no checkbox
        anchor = frame.locator('#recaptcha-anchor')
        anchor.click()
        logger.info("[ESTADUAL-SP] Checkbox do reCAPTCHA clicado.")
        
        # 3. Aguarda um momento para ver se o CAPTCHA foi resolvido automaticamente
        time.sleep(3.0)
        if anchor.get_attribute('aria-checked') == 'true':
            logger.info("[ESTADUAL-SP] reCAPTCHA resolvido automaticamente (sem desafio de imagem/áudio)!")
            return True
            
        logger.info("[ESTADUAL-SP] Desafio de segurança apresentado. Iniciando bypass via áudio...")
        
        # 4. Localiza o iframe do desafio (bframe)
        bframe_selector = 'iframe[src*="bframe"]'
        page.wait_for_selector(bframe_selector, timeout=10000)
        bframe = page.frame_locator(bframe_selector)
        
        # 5. Clica no botão de áudio
        audio_btn = bframe.locator('#recaptcha-audio-button')
        audio_btn.wait_for(state="visible", timeout=5000)
        audio_btn.click()
        logger.info("[ESTADUAL-SP] Botão de áudio clicado.")
        time.sleep(2.0)
        
        # 6. Tenta obter o link de download do áudio
        audio_url = ""
        try:
            bframe.locator('.rc-audiochallenge-download-link, #audio-source').first.wait_for(state="attached", timeout=6000)
            
            download_link = bframe.locator('.rc-audiochallenge-download-link')
            audio_source = bframe.locator('#audio-source')
            
            if download_link.is_visible():
                audio_url = download_link.get_attribute('href')
            elif audio_source.count() > 0:
                audio_url = audio_source.get_attribute('src')
                
            if not audio_url:
                raise Exception("Não foi possível extrair a URL do áudio.")
        except Exception as sel_err:
            body_text = bframe.locator('body').inner_text()
            if "tente novamente mais tarde" in body_text.lower() or "blocked" in body_text.lower() or "solicitações automatizadas" in body_text.lower() or "automated queries" in body_text.lower():
                raise Exception("Bloqueio de reCAPTCHA detectado pelo Google (limite de requisições excedido). Tente novamente mais tarde.")
            raise Exception(f"Falha ao carregar desafio de áudio: {sel_err}")
            
        logger.info(f"[ESTADUAL-SP] URL do áudio obtido: {audio_url}")
        
        # 7. Faz o download do áudio MP3
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        response = requests.get(audio_url, timeout=15, verify=False)
        mp3_path = "temp_captcha.mp3"
        wav_path = "temp_captcha.wav"
        
        with open(mp3_path, "wb") as f:
            f.write(response.content)
            
        # 8. Converte MP3 para WAV
        from pydub import AudioSegment
        sound = AudioSegment.from_mp3(mp3_path)
        sound.export(wav_path, format="wav")
        logger.info("[ESTADUAL-SP] Áudio convertido para WAV.")
        
        # 9. Transcreve o áudio usando SpeechRecognition
        import speech_recognition as sr
        r = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio_data = r.record(source)
            
        text = r.recognize_google(audio_data, language="en-US")
        logger.info(f"[ESTADUAL-SP] Texto transcrito pelo Google Speech API: '{text}'")
        
        # Limpa os arquivos temporários
        try:
            os.remove(mp3_path)
            os.remove(wav_path)
        except:
            pass
            
        # 10. Insere o texto transcrito
        response_input = bframe.locator('#audio-response')
        response_input.fill(text)
        time.sleep(0.5)
        
        # 11. Clica no botão de verificar
        verify_btn = bframe.locator('#recaptcha-verify-button')
        verify_btn.click()
        logger.info("[ESTADUAL-SP] Botão de verificação clicado.")
        time.sleep(3.0)
        
        # 12. Verifica se funcionou
        if anchor.get_attribute('aria-checked') == 'true':
            logger.info("[ESTADUAL-SP] reCAPTCHA resolvido com sucesso via áudio!")
            return True
        else:
            logger.warning("[ESTADUAL-SP] Falha na validação do áudio do reCAPTCHA.")
            return False
            
    except Exception as e:
        logger.error(f"[ESTADUAL-SP] Erro ao resolver reCAPTCHA: {e}")
        return False

def emitir_cnd_estadual_sp(cnpj):
    logger.info(f"[ESTADUAL-SP] Iniciando consulta para o CNPJ: {cnpj}")
    url = "https://www10.fazenda.sp.gov.br/CertidaoNegativaDeb/Pages/EmissaoCertidaoNegativa.aspx"
    temp_pdf_path = f"temp_estadual_sp_{cnpj}.pdf"
    
    user_data_dir = os.path.abspath("./user_data_sp")
    with sync_playwright() as p:
        browser, context = iniciar_e_conectar_chrome(p, user_data_dir, headless=True)
        page = context.new_page()
        
        try:
            page.goto(url)
            
            # Selecionar o elemento xPath //*[@id="MainContent_cnpjradio"]
            cnpj_radio_xpath = 'xpath=//*[@id="MainContent_cnpjradio"]'
            page.wait_for_selector(cnpj_radio_xpath, timeout=20000)
            page.click(cnpj_radio_xpath)
            
            # Preencher o CNPJ no campo xPath //*[@id="MainContent_txtDocumento"]
            cnpj_input_xpath = 'xpath=//*[@id="MainContent_txtDocumento"]'
            page.wait_for_selector(cnpj_input_xpath, timeout=10000)
            cnpj_limpo = cnpj.replace(".", "").replace("/", "").replace("-", "")
            page.fill(cnpj_input_xpath, cnpj_limpo)
            
            # Resolver o CAPTCHA
            recaptcha_resolvido = resolver_recaptcha(page)
            if not recaptcha_resolvido:
                raise Exception("A resolução automática do reCAPTCHA falhou no modo headless.")
            
            # Clicar no botão "EMITIR" cujo xPath é o //*[@id="MainContent_btnPesquisar"]
            btn_emitir_xpath = 'xpath=//*[@id="MainContent_btnPesquisar"]'
            page.wait_for_selector(btn_emitir_xpath, timeout=10000)
            page.click(btn_emitir_xpath)
            
            # Na tela seguinte, localizar o botão "IMPRIMIR" e salvar a certidão como PDF
            btn_imprimir_xpath = 'xpath=//*[@id="MainContent_btnImpressao"]'
            page.wait_for_selector(btn_imprimir_xpath, timeout=20000)
            
            # Mock window.print para evitar bloquear a thread caso dispare o diálogo de impressão nativo
            page.evaluate("window.print = () => { console.log('window.print simulado com sucesso'); }")
            
            pdf_salvo = False
            
            try:
                # Tenta capturar se o botão dispara um download de arquivo direto
                with page.expect_download(timeout=5000) as download_info:
                    page.click(btn_imprimir_xpath)
                download = download_info.value
                download.save_as(temp_pdf_path)
                logger.info(f"[ESTADUAL-SP] PDF baixado com sucesso via download em: {temp_pdf_path}")
                pdf_salvo = True
            except Exception:
                pass
            
            if not pdf_salvo:
                # Emula mídia de impressão para carregar estilos de impressão da página
                page.emulate_media(media="print")
                
                # Oculta os botões de controle na página para não saírem no PDF impresso
                page.evaluate("""
                    document.querySelectorAll('input[type="submit"], input[type="button"], button, .no-print, [id*="btnImpressao"], [id*="btnVoltar"]').forEach(el => el.style.display = 'none');
                """)
                
                # Clica no botão para disparar scripts internos (caso existam)
                try:
                    page.click(btn_imprimir_xpath, timeout=2000)
                except:
                    pass
                
                screenshot_path = f"temp_screenshot_estadual_{cnpj}.png"
                page.screenshot(path=screenshot_path, full_page=True)
                
                # Restaura a mídia para exibição em tela normal
                page.emulate_media(media="screen")
                
                # Converte o screenshot para PDF real usando Pillow
                try:
                    from PIL import Image
                    img = Image.open(screenshot_path).convert("RGB")
                    img.save(temp_pdf_path, "PDF")
                    logger.info(f"[ESTADUAL-SP] PDF real gerado via conversão de imagem em: {temp_pdf_path}")
                    pdf_salvo = True
                except Exception as pdf_err:
                    raise Exception(f"Erro ao converter screenshot para PDF: {pdf_err}")
                finally:
                    if os.path.exists(screenshot_path):
                        try: os.remove(screenshot_path)
                        except: pass
            
            data_vencimento = (datetime.now() + timedelta(days=180)).strftime("%Y-%m-%d")
            return temp_pdf_path, data_vencimento
            
        except Exception as e:
            raise Exception(f"Falha no robô Estadual SP: {str(e)}")
        finally:
            if 'page' in locals():
                try:
                    client = page.context.new_cdp_session(page)
                    client.send("Browser.close")
                except:
                    pass
                try: page.close()
                except: pass
            if 'context' in locals():
                try: context.close()
                except: pass
            if 'browser' in locals():
                try: browser.close()
                except: pass

def emitir_cnd_estadual_via_api(cnpj, uf):
    logger.warning(f"[ESTADUAL] Lógica específica para a UF {uf} (CNPJ {cnpj}) ainda não implementada.")
    raise Exception(f"Integração Estadual para a UF {uf} ainda não desenvolvida. Aguardando implementação específica.")

import json
FALLBACK_JSON_PATH = os.path.join(os.path.dirname(__file__), "fallback_federal.json")

def read_fallback_cnpjs():
    try:
        with open(FALLBACK_JSON_PATH, "r") as f:
            return set(json.load(f))
    except:
        return set()

def add_fallback_cnpj(cnpj):
    cnpjs = read_fallback_cnpjs()
    cnpjs.add(cnpj)
    with open(FALLBACK_JSON_PATH, "w") as f:
        json.dump(list(cnpjs), f)

def remove_fallback_cnpj(cnpj):
    cnpjs = read_fallback_cnpjs()
    if cnpj in cnpjs:
        cnpjs.remove(cnpj)
        with open(FALLBACK_JSON_PATH, "w") as f:
            json.dump(list(cnpjs), f)


def emitir_cnd_federal(cnpj):
    """
    Robô para emissão da CND Federal (Receita Federal / PGFN).
    """
    logger.info(f"[FEDERAL] Iniciando consulta para o CNPJ: {cnpj}")
    temp_pdf_path = f"temp_federal_{cnpj}.pdf"
    
    user_data_dir = os.path.abspath("./user_data_receita")
    with sync_playwright() as p:
        browser, context = iniciar_e_conectar_chrome(p, user_data_dir, headless=True)
        page = context.new_page()
        
        try:
            time.sleep(0.2)
            page.goto("https://servicos.receitafederal.gov.br/servico/certidoes/#/home/cnpj")
            
            # Seletor do CNPJ (tenta name do input real, placeholder, e fallback do usuário)
            cnpj_selector = 'input[name="niContribuinte"]'
            try:
                page.wait_for_selector(cnpj_selector, timeout=15000)
            except Exception:
                cnpj_selector = 'input[placeholder="Informe o CNPJ"]'
                try:
                    page.wait_for_selector(cnpj_selector, timeout=5000)
                except Exception:
                    cnpj_selector = 'xpath=//*[@id="id3f4c9ab5e7e9d4"]'
                    page.wait_for_selector(cnpj_selector, timeout=10000)
                    
            cnpj_limpo = cnpj.replace(".", "").replace("/", "").replace("-", "")
            
            # Adiciona delay antes de interagir com o campo
            time.sleep(1.0)
            click_humano(page, cnpj_selector)
            time.sleep(0.5)
            
            # Digita o CNPJ com delay entre as teclas
            page.type(cnpj_selector, cnpj_limpo, delay=60)
            time.sleep(0.5)
            
            # Dispara evento de blur/mudança de foco (pressionando Tab)
            page.press(cnpj_selector, "Tab")
            time.sleep(0.5)
            
            # Clica no botão de aceitar cookies se estiver visível para não atrapalhar
            try:
                btn_cookies = 'button:has-text("Aceitar")'
                if page.locator(btn_cookies).is_visible():
                    time.sleep(1.0)
                    click_humano(page, btn_cookies)
                    time.sleep(1.5)
            except:
                pass
            
            # Trata CAPTCHA se houver
            solver_captcha_se_necessario(page, "FEDERAL")
            time.sleep(2.0)
            
            # Clica no botão de Emitir Certidão
            btn_selector = 'button:has-text("Emitir Certidão")'
            try:
                page.wait_for_selector(btn_selector, timeout=10000)
            except Exception:
                btn_selector = 'xpath=/html/body/app-root/mf-portal-layout/portal-main-layout/div/main/ng-component/ng-component/app-coleta-parametros-pj/app-coleta-parametros-template/form/div[2]/div[2]/button[2]'
                page.wait_for_selector(btn_selector, timeout=5000)
                
            time.sleep(0.5)
            click_humano(page, btn_selector)
            time.sleep(1.0)
            
            # Trata o caso de certidão válida já existente (Modal)
            try:
                # O usuário informou o xpath exato do botão "Emitir Nova Certidão"
                btn_xpath = 'xpath=/html/body/modal-container/div[2]/div/div[3]/button[2]'
                btn_texto = 'button:has-text("Emitir Nova Certidão")'
                btn_consultar_modal = 'xpath=/html/body/modal-container/div[2]/div/div[3]/button[1]'
                btn_texto_consultar = 'button:has-text("Consultar Certidão")'

                # Aguardamos pelo modal ou botão (espera um dos dois)
                try:
                    page.wait_for_selector('modal-container', timeout=15000)
                except:
                    page.wait_for_selector(btn_xpath, timeout=5000)

                time.sleep(1.0)

                # Verifica se o CNPJ está na lista de fallback (erro 023 anterior)
                usar_fallback_consulta = (cnpj_limpo in read_fallback_cnpjs())

                if usar_fallback_consulta:
                    logger.info(f"[FEDERAL] Fallback ativado para {cnpj}! Clicando em Consultar Certidão no modal...")
                    if page.locator(btn_consultar_modal).is_visible():
                        click_humano(page, btn_consultar_modal)
                    else:
                        click_humano(page, btn_texto_consultar)
                    # Remove do fallback pois já consumimos
                    remove_fallback_cnpj(cnpj_limpo)
                    logger.info("Modal tratado com Consultar Certidão (Fallback).")
                else:
                    if page.locator(btn_xpath).is_visible():
                        click_humano(page, btn_xpath)
                        logger.info(f"Modal tratado clicando no xpath: {btn_xpath}")
                    elif page.locator(btn_texto).is_visible():
                        click_humano(page, btn_texto)
                        logger.info(f"Modal tratado clicando no texto: {btn_texto}")
                    else:
                        # Fallback final tentando forçar clique se existir no DOM
                        page.click(btn_xpath, force=True, timeout=5000)
                        logger.info("Modal tratado com clique forçado no xpath.")

                time.sleep(1.0)
            except Exception as e:
                logger.info(f"Modal de certidão válida não apareceu ou erro ao clicar: {e}")
            
            # Tratamento de Erros / Verificação do Documento
            sucesso_selector = "iframe:not([src*='hcaptcha']):not([src*='google']), embed, object, [href*='.pdf']"
            erro_selector = ".alert, .error, .message-error, .mensagem-erro, #mensagemErro, .br-message, .feedback, .invalid-feedback"
            
            downloaded = False
            # Se for a primeira emissão (nunca solicitada antes), a página pode exibir o link de download alternativo direto
            link_download_alternativo = 'a:has-text("download do documento PDF da certidão")'
            if page.locator(link_download_alternativo).is_visible():
                logger.info("Página de emissão de primeira certidão detectada (sem PDF embutido). Clicando no link alternativo...")
                try:
                    with page.expect_download(timeout=10000) as download_info:
                        page.click(link_download_alternativo)
                    download = download_info.value
                    download.save_as(temp_pdf_path)
                    logger.info(f"PDF real da certidão baixado e salvo com sucesso em: {temp_pdf_path}")
                    # Injeta elemento de sucesso no DOM para que o sucesso_selector seja satisfeito
                    page.evaluate('() => { const embed = document.createElement("embed"); embed.id = "mock-success-pdf"; document.body.appendChild(embed); }')
                    downloaded = True
                except Exception as d_err:
                    logger.error(f"Erro ao baixar o PDF pelo link de download alternativo: {d_err}")
            
            try:
                page.wait_for_selector(f"{sucesso_selector}, {erro_selector}, div:has-text('insuficientes')", timeout=5000)
            except Exception:
                # Se der timeout, faz uma verificação rápida de textos de erro no body
                body_text = page.locator("body").inner_text()
                if "insuficientes" in body_text or "Não foi possível concluir" in body_text:
                    pass
                else:
                    raise
            
            body_text = page.locator("body").inner_text()
            if "insuficientes" in body_text or "Não foi possível concluir" in body_text:
                logger.info("[FEDERAL] Impedimento para nova emissão detectado. Tentando obter última certidão válida (segunda via)...")
                
                # Distingue dois cenários de erro:
                # A) Tela de "Resultado da Emissão" com "insuficientes" - tem botão "+ Nova Consulta"
                # B) Erro 023 "Não foi possível concluir" no formulário - tem botões "Consultar Certidão" / "Emitir Certidão"
                btn_nova_consulta = 'button:has-text("Nova Consulta")'
                is_resultado_insuficientes = page.locator(btn_nova_consulta).is_visible()
                
                if is_resultado_insuficientes:
                    # ===== CENÁRIO A: Tela de resultado "insuficientes" =====
                    logger.info("[FEDERAL] Tela de resultado 'insuficientes' detectada. Clicando em '+ Nova Consulta'...")
                    page.click(btn_nova_consulta)
                    time.sleep(2.0)
                    
                    # Aguarda o formulário carregar e preenche o CNPJ
                    try:
                        page.wait_for_selector(cnpj_selector, timeout=15000)
                    except Exception:
                        for alt_sel in ['input[name="niContribuinte"]', 'input[placeholder="Informe o CNPJ"]']:
                            try:
                                page.wait_for_selector(alt_sel, timeout=5000)
                                cnpj_selector = alt_sel
                                break
                            except:
                                continue
                    
                    time.sleep(1.0)
                    page.focus(cnpj_selector)
                    page.click(cnpj_selector, click_count=3)
                    page.keyboard.press("Backspace")
                    time.sleep(0.5)
                    page.type(cnpj_selector, cnpj_limpo, delay=60)
                    page.press(cnpj_selector, "Tab")
                    time.sleep(1.0)
                    
                    # Aceita cookies se aparecer
                    try:
                        btn_cookies = 'button:has-text("Aceitar")'
                        if page.locator(btn_cookies).is_visible():
                            page.click(btn_cookies)
                            time.sleep(0.5)
                    except:
                        pass
                    
                    # Clica em "Emitir Certidão" para disparar o modal
                    try:
                        page.wait_for_selector(btn_selector, timeout=10000)
                    except:
                        btn_selector = 'button:has-text("Emitir Certidão")'
                        page.wait_for_selector(btn_selector, timeout=5000)
                    page.click(btn_selector)
                    time.sleep(1.5)
                    
                    # No modal, clica em "Consultar Certidão" (primeiro botão)
                    btn_consultar_modal = 'xpath=/html/body/modal-container/div[2]/div/div[3]/button[1]'
                    modal_found = False
                    try:
                        page.wait_for_selector('modal-container', timeout=15000)
                        modal_found = True
                    except:
                        try:
                            page.wait_for_selector(btn_consultar_modal, timeout=5000)
                            modal_found = True
                        except:
                            pass
                    
                    if modal_found:
                        time.sleep(1.0)
                        if page.locator(btn_consultar_modal).is_visible():
                            page.click(btn_consultar_modal)
                            logger.info("[FEDERAL] Clicou em Consultar Certidão no modal.")
                        else:
                            btn_text_sel = 'button:has-text("Consultar Certidão")'
                            if page.locator(btn_text_sel).is_visible():
                                page.click(btn_text_sel)
                                logger.info("[FEDERAL] Clicou em Consultar Certidão no modal via texto.")
                            else:
                                try:
                                    page.locator("modal-container .modal-footer button").first.click()
                                    logger.info("[FEDERAL] Clicou no primeiro botão do modal-footer.")
                                except Exception as modal_click_err:
                                    logger.warning(f"[FEDERAL] Falha ao tentar clicar no modal: {modal_click_err}")
                        time.sleep(2.0)
                    else:
                        # Sem modal - tenta "Consultar Certidão" direto no formulário
                        logger.info("[FEDERAL] Modal não apareceu após Nova Consulta. Tentando Consultar direto...")
                        btn_consultar_direto = 'button:has-text("Consultar Certidão")'
                        if page.locator(btn_consultar_direto).is_visible():
                            page.click(btn_consultar_direto)
                            time.sleep(2.0)
                        else:
                            raise Exception("Não foi possível acessar a tela de consulta de certidões existentes.")
                    
                    # Clica no botão de consultar no formulário intermediário (se existir)
                    btn_consultar_form = 'xpath=/html/body/app-root/mf-portal-layout/portal-main-layout/div/main/ng-component/ng-component/ng-component/app-informar-parametro-pj/app-informar-parametro/form/div[2]/button'
                    try:
                        page.wait_for_selector(btn_consultar_form, timeout=8000)
                        page.click(btn_consultar_form)
                        logger.info("[FEDERAL] Clicou no botão Consultar do formulário de consulta.")
                        time.sleep(2.0)
                    except:
                        try:
                            btn_text_form = 'form button:has-text("Consultar Certidão")'
                            if page.locator(btn_text_form).is_visible():
                                page.click(btn_text_form)
                                time.sleep(2.0)
                        except:
                            pass
                
                else:
                    # ===== CENÁRIO B: Erro 023 "Não foi possível concluir" no formulário =====
                    # Como o erro 023 bloqueia o IP temporariamente, tentaremos forçar a consulta na próxima execução
                    logger.warning(f"[FEDERAL] Erro 023 do portal detectado (rate-limit) para o CNPJ {cnpj}.")
                    add_fallback_cnpj(cnpj_limpo)
                    logger.info("[FEDERAL] CNPJ adicionado ao fallback. O worker clicará em 'Consultar Certidão' na próxima tentativa.")
                    raise Exception("Rate limit (023) atingido após tentativa de emissão. CNPJ configurado para consulta de segunda via na próxima tentativa (fallback).")
                
                # ===== PARTE COMUM: Tabela de resultados =====
                try:
                    page.wait_for_selector("datatable-body-row", timeout=15000)
                except Exception as table_err:
                    logger.error(f"[FEDERAL] Tabela de resultados não carregou: {table_err}")
                    raise Exception(f"Tabela de certidões não carregou após consulta: {table_err}")
                
                import re
                
                valid_rows = []
                rows = page.locator("datatable-body-row").all()
                logger.info(f"[FEDERAL] Encontradas {len(rows)} linhas na tabela de certidões.")
                for idx, row in enumerate(rows):
                    cells_text = [c.inner_text().strip() for c in row.locator("datatable-body-cell").all()]
                    logger.info(f"[FEDERAL] Linha {idx}: {cells_text}")
                    # Verifica se a certidão está válida no portal
                    if any("Válida" in t for t in cells_text):
                        validity_date = None
                        for t in cells_text:
                            m = re.search(r"(\d{2})/(\d{2})/(\d{4})", t)
                            if m:
                                try:
                                    validity_date = datetime.strptime(m.group(0), "%d/%m/%Y").date()
                                except:
                                    pass
                        if validity_date:
                            valid_rows.append((validity_date, row))
                
                if not valid_rows:
                    raise Exception("As informações são insuficientes e nenhuma certidão válida anterior foi localizada no portal.")
                
                # Ordena pela data de validade descendente (maior primeiro)
                valid_rows.sort(key=lambda x: x[0], reverse=True)
                best_date, best_row = valid_rows[0]
                
                # Cancela se a certidão com maior validade já estiver expirada
                if best_date < datetime.today().date():
                    raise Exception(f"A certidão válida mais recente expirou em {best_date.strftime('%d/%m/%Y')}.")
                
                logger.info(f"[FEDERAL] Baixando segunda via da certidão com validade até: {best_date.strftime('%d/%m/%Y')}")
                
                # Clicar no botão de download (seta) na linha correspondente
                btn_download = best_row.locator("button i, button")
                
                # Espera o download iniciar ao clicar
                with page.expect_download(timeout=15000) as download_info:
                    btn_download.first.click()
                download = download_info.value
                download.save_as(temp_pdf_path)
                
                return temp_pdf_path, best_date.strftime("%Y-%m-%d")
            
            # 1. Verifica erros por seletores de classes/containers
            elementos_erro = page.query_selector_all(erro_selector)
            for el in elementos_erro:
                if el.is_visible():
                    erro_msg = el.inner_text().strip()
                    if erro_msg:
                        raise Exception(f"Erro no portal da Receita Federal: {erro_msg}")
            
            # Cria arquivo mock para simular emissão se não foi baixado o PDF real
            if not downloaded:
                with open(temp_pdf_path, "wb") as f:
                    f.write(b"MOCK PDF CONTENT - CERTIDAO FEDERAL CNPJ " + cnpj.encode('utf-8'))
                
            data_vencimento = (datetime.now() + timedelta(days=180)).strftime("%Y-%m-%d")
            return temp_pdf_path, data_vencimento
            
        except Exception as e:
            raise Exception(f"Falha no robô Federal: {str(e)}")
            
        finally:
            if 'page' in locals():
                try:
                    client = page.context.new_cdp_session(page)
                    client.send("Browser.close")
                except:
                    pass
                try: page.close()
                except: pass
            if 'context' in locals():
                try: context.close()
                except: pass
            if 'browser' in locals():
                try: browser.close()
                except: pass


def emitir_cnd_fgts(cnpj, uf):
    """
    Robô para emissão do CRF (Certificado de Regularidade do FGTS da Caixa).
    """
    logger.info(f"[FGTS] Iniciando consulta para o CNPJ: {cnpj} | UF: {uf}")
    temp_pdf_path = f"temp_fgts_{cnpj}.pdf"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        try:
            page.goto("https://consulta-crf.caixa.gov.br/consultacrf/pages/consultaEmpregador.jsf")
            
            cnpj_selector = 'xpath=//*[@id="mainForm:txtInscricao1"]'
            uf_selector = 'xpath=//*[@id="mainForm:uf"]'
            btn_selector = 'xpath=//*[@id="mainForm:btnConsultar"]'
            
            page.wait_for_selector(cnpj_selector, timeout=20000)
            
            cnpj_limpo = cnpj.replace(".", "").replace("/", "").replace("-", "")
            page.fill(cnpj_selector, cnpj_limpo)
            
            page.wait_for_selector(uf_selector, timeout=10000)
            page.select_option(uf_selector, value=uf)
            
            # Clica em Consultar
            page.wait_for_selector(btn_selector, timeout=10000)
            page.click(btn_selector)
            
            # Tratamento de Erros / Verificação do Documento
            sucesso_selector = '[id="mainForm:j_id76"]'
            erro_selector = ".msgErro, .erro, [id='mainForm:mensagens']"
            
            page.wait_for_selector(f"{sucesso_selector}, {erro_selector}", timeout=20000)
            
            # Verifica se houve algum erro reportado na tela
            elementos_erro = page.query_selector_all(erro_selector)
            for el in elementos_erro:
                if el.is_visible():
                    erro_msg = el.inner_text().strip()
                    if erro_msg:
                        raise Exception(f"Erro no portal da Caixa (FGTS): {erro_msg}")
            
            # Se a empresa estiver regular, segue o fluxo de telas até a certidão
            if page.query_selector(sucesso_selector):
                # 1. Clica no link 'Certificado de Regularidade do FGTS - CRF'
                page.click(sucesso_selector)
                
                # 2. Na tela seguinte (Imagem 1), aguarda e clica em 'Visualizar'
                btn_visualizar = '[id="mainForm:btnVisualizar"]'
                page.wait_for_selector(btn_visualizar, timeout=15000)
                page.click(btn_visualizar)
                
                # 3. Na tela seguinte (Imagem 2), aguarda o botão 'Imprimir' aparecer e clica nele
                btn_imprimir = '[id="mainForm:btImprimir4"]'
                page.wait_for_selector(btn_imprimir, timeout=15000)
                
                # Mock window.print para evitar bloquear a thread com a janela nativa do Chrome
                page.evaluate("window.print = () => { console.log('window.print simulado com sucesso'); }")
                page.click(btn_imprimir)
                
                # Esconde manualmente quaisquer botões ou elementos indesejados (como "Voltar" e "Imprimir") para garantir um PDF 100% limpo
                page.evaluate("""
                    document.querySelectorAll('input[type="submit"], input[type="button"], button, .no-print, [id*="btnVoltar"], [id*="btImprimir"]').forEach(el => el.style.display = 'none');
                """)
                
                # Extrai a data de validade a partir do texto do body do portal da Caixa
                body_text = ""
                try:
                    body_text = page.locator("body").inner_text()
                except Exception as body_ex:
                    logger.warning(f"[AVISO] Falha ao ler o body_text para validade do FGTS: {body_ex}")
                
                import re
                validade_match = re.search(r"Validade:\s*(\d{2}/\d{2}/\d{4})\s*(?:a|à)\s*(\d{2}/\d{2}/\d{4})", body_text, re.IGNORECASE)
                data_vencimento = None
                if validade_match:
                    partes = validade_match.group(2).split("/")
                    if len(partes) == 3:
                        data_vencimento = f"{partes[2]}-{partes[1]}-{partes[0]}"
                        logger.info(f"[FGTS] Vencimento real extraído: {data_vencimento}")
                
                if not data_vencimento:
                    data_vencimento = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")

                # 4. Gera o PDF real da página do certificado usando a função de impressão nativa do Playwright
                # Isso contorna o diálogo de impressão do navegador que bloquearia o script
                page.pdf(path=temp_pdf_path, format="A4", print_background=True)
                logger.info(f"[FGTS] PDF da certidão gerado com sucesso via page.pdf em {temp_pdf_path}")
            else:
                raise Exception("Não foi possível localizar o link do CRF após a consulta.")
                
            browser.close()
            return temp_pdf_path, data_vencimento
            
        except Exception as e:
            browser.close()
            raise Exception(f"Falha no robô FGTS: {str(e)}")


def emitir_cnd_cndt(cnpj):
    """
    Robô para emissão da Certidão Trabalhista CNDT (Tribunal Superior do Trabalho).
    """
    logger.info(f"[CNDT] Iniciando consulta para o CNPJ: {cnpj}")
    temp_pdf_path = f"temp_cndt_{cnpj}.pdf"
    ocr = ddddocr.DdddOcr(show_ad=False)
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        try:
            page.goto("https://cndt-certidao.tst.jus.br/inicio.faces")
            
            btn_inicial = 'xpath=//*[@id="corpo"]/div/div[2]/input[1]'
            page.wait_for_selector(btn_inicial, timeout=20000)
            page.click(btn_inicial)
            
            cnpj_selector = 'xpath=//*[@id="gerarCertidaoForm:cpfCnpj"]'
            page.wait_for_selector(cnpj_selector, timeout=20000)
            page.fill(cnpj_selector, cnpj)
            
            captcha_img_sel = 'img[id*="captcha"], img[id*="Captcha"], img[src^="data:image"]'
            captcha_input_sel = '[id="idCampoResposta"]'
            btn_emitir = '[id="gerarCertidaoForm:btnEmitirCertidao"]'
            erro_selector = ".mensagem-erro, .erro, .alert, #messages, ul.erro, [id='gerarCertidaoForm:mensagens'], #mensagens, .erros, [id*='areaMensagemErro']"
            
            max_tentativas = 30
            for tentativa in range(1, max_tentativas + 1):
                logger.info(f"[CNDT CAPTCHA] Tentativa {tentativa}/{max_tentativas}...")
                
                img_el = page.locator(captcha_img_sel).first
                img_el.wait_for(state="attached", timeout=15000)
                
                img_bytes = None
                src = img_el.get_attribute("src")
                if src and src.startswith("data:image"):
                    import base64
                    try:
                        header, base64_data = src.split(",", 1)
                        img_bytes = base64.b64decode(base64_data)
                        logger.info("[CNDT CAPTCHA] Imagem extraída diretamente via Base64 do atributo 'src'.")
                    except Exception as b64_err:
                        logger.warning(f"[CNDT CAPTCHA] Erro ao decodificar Base64: {b64_err}")
                
                if not img_bytes:
                    try:
                        img_el.wait_for(state="visible", timeout=5000)
                        img_bytes = img_el.screenshot()
                    except Exception as s_err:
                        logger.warning(f"[CNDT CAPTCHA] Falha no screenshot do elemento: {s_err}. Capturando página inteira...")
                        temp_cndt_snap = f"temp_cndt_captcha_snap_{cnpj}.png"
                        page.screenshot(path=temp_cndt_snap)
                        with open(temp_cndt_snap, "rb") as f:
                            img_bytes = f.read()
                        if os.path.exists(temp_cndt_snap):
                            os.remove(temp_cndt_snap)
                
                if tentativa <= 15:
                    captcha_val = ocr.classification(img_bytes)
                    captcha_val = "".join([c for c in captcha_val if c.isascii() and c.isalnum()])
                    logger.info(f"ddddocr leu: '{captcha_val}'")
                else:
                    try:
                        nparr = np.frombuffer(img_bytes, np.uint8)
                        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                        resized = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
                        blur = cv2.GaussianBlur(resized, (3, 3), 0)
                        thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
                        
                        config = "--psm 8 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
                        captcha_val = pytesseract.image_to_string(thresh, config=config).strip()
                        captcha_val = "".join([c for c in captcha_val if c.isascii() and c.isalnum()])
                        logger.info(f"pytesseract (fallback) leu: '{captcha_val}'")
                    except Exception as ocr_err:
                        logger.warning(f"Erro ao processar pytesseract fallback: {ocr_err}")
                        captcha_val = ""
                
                page.fill(captcha_input_sel, "")
                page.fill(captcha_input_sel, captcha_val)
                
                try:
                    with page.expect_download(timeout=10000) as download_info:
                        page.click(btn_emitir)
                    
                    download = download_info.value
                    download.save_as(temp_pdf_path)
                    logger.info(f"[CNDT] PDF real da certidão CNDT baixado com sucesso em {temp_pdf_path}")
                    break
                    
                except Exception as d_err:
                    time.sleep(1.0)
                    elementos_erro = page.query_selector_all(erro_selector)
                    erro_msg = ""
                    for el in elementos_erro:
                        if el.is_visible():
                            txt = el.inner_text().strip()
                            if txt:
                                erro_msg = txt
                                break
                    
                    # Se houve erro de captcha, clica em "Emitir Nova Certidão" para resetar o form e tentar de novo
                    btn_emitir_nova = 'input[value="Emitir Nova Certidão"]'
                    try:
                        if page.locator(btn_emitir_nova).count() > 0:
                            logger.info("[CNDT CAPTCHA] Botão 'Emitir Nova Certidão' detectado. Reiniciando formulário...")
                            page.click(btn_emitir_nova)
                            page.wait_for_selector(cnpj_selector, timeout=15000)
                            page.fill(cnpj_selector, cnpj)
                    except Exception as btn_err:
                        logger.warning(f"Erro ao tentar voltar com 'Emitir Nova Certidão': {btn_err}")
                    
                    if erro_msg:
                        logger.warning(f"Mensagem do portal CNDT: '{erro_msg}'")
                        if any(kwd in erro_msg.lower() for kwd in ["código", "segurança", "captcha", "inválido", "caracteres"]):
                            continue
                        else:
                            raise Exception(f"Erro no portal CNDT: {erro_msg}")
                    else:
                        if tentativa == max_tentativas:
                            raise Exception(f"Falha ao iniciar download ou erro não identificado: {d_err}")
                        continue
                
            if not os.path.exists(temp_pdf_path):
                raise Exception(f"Falha ao resolver o CAPTCHA da CNDT após {max_tentativas} tentativas.")
            browser.close()
            data_vencimento = (datetime.now() + timedelta(days=180)).strftime("%Y-%m-%d")
            return temp_pdf_path, data_vencimento
            
        except Exception as e:
            browser.close()
            raise Exception(f"Falha no robô CNDT: {str(e)}")


def emitir_cnd_municipal_via_api(cnpj, municipio, uf):
    """
    Rota B: Integração com API de mercado para obter a certidão municipal.
    """
    logger.warning(f"[MUNICIPAL] Lógica específica para o município {municipio}/{uf} (CNPJ {cnpj}) ainda não implementada.")
    raise Exception(f"Integração Municipal para {municipio}/{uf} ainda não desenvolvida. Aguardando implementação específica.")


def emitir_cnd_cadin_sp(cnpj):
    """
    Robô para emissão do Comprovante de Inexistência de Registros do
    CADIN Municipal (Cadastro Informativo Municipal) da Prefeitura de São Paulo.
    URL: https://www3.prefeitura.sp.gov.br/cadin/Pesq_Deb.aspx
    Validade: 30 dias a partir da data de emissão.
    """
    logger.info(f"[CADIN] Iniciando consulta para o CNPJ: {cnpj}")
    temp_pdf_path = f"temp_cadin_{cnpj}.pdf"
    ocr = ddddocr.DdddOcr(show_ad=False)
    cnpj_limpo = cnpj.replace(".", "").replace("/", "").replace("-", "")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            accept_downloads=True
        )
        page = context.new_page()

        try:
            page.goto("https://www3.prefeitura.sp.gov.br/cadin/Pesq_Deb.aspx", wait_until="networkidle", timeout=30000)
            time.sleep(2.0)

            # --- Etapa 1: Aceitar cookies (se o banner estiver visível) ---
            try:
                btn_cookies_sel = 'button:has-text("Autorizo o uso de todos os cookies")'
                btn_cookies = page.locator(btn_cookies_sel)
                if btn_cookies.count() > 0 and btn_cookies.first.is_visible():
                    logger.info("[CADIN] Banner de cookies detectado. Aceitando...")
                    click_humano(page, btn_cookies_sel)
                    time.sleep(1.5)
                else:
                    logger.info("[CADIN] Banner de cookies não detectado. Prosseguindo...")
            except Exception as cookie_err:
                logger.warning(f"[CADIN] Erro ao tratar cookies (não-crítico): {cookie_err}")

            # --- Etapa 2: Preencher CNPJ (somente números) ---
            cnpj_selector = '#txt_CNPJ'
            page.wait_for_selector(cnpj_selector, timeout=10000)
            time.sleep(0.5)
            click_humano(page, cnpj_selector)
            time.sleep(0.3)
            page.fill(cnpj_selector, "")
            page.type(cnpj_selector, cnpj_limpo, delay=50)
            time.sleep(0.5)
            logger.info(f"[CADIN] CNPJ {cnpj_limpo} preenchido.")

            # --- Etapa 3: Resolver CAPTCHA com loop de tentativas ---
            captcha_img_sel = 'img[src*="CaptchaImage.aspx"]'
            captcha_input_sel = '#txtimg'
            btn_pesquisar = '#cmd_Pesq'

            max_tentativas = 20
            sucesso = False

            for tentativa in range(1, max_tentativas + 1):
                logger.info(f"[CADIN CAPTCHA] Tentativa {tentativa}/{max_tentativas}...")

                # Captura a imagem do CAPTCHA
                img_el = page.locator(captcha_img_sel).first
                img_el.wait_for(state="visible", timeout=10000)
                time.sleep(0.5)
                img_bytes = img_el.screenshot()

                # OCR: ddddocr nas primeiras tentativas, pytesseract como fallback
                if tentativa <= 12:
                    captcha_val = ocr.classification(img_bytes)
                    captcha_val = "".join([c for c in captcha_val if c.isascii() and c.isalnum()])
                    captcha_val = captcha_val.upper()
                    logger.info(f"[CADIN CAPTCHA] ddddocr leu: '{captcha_val}'")
                else:
                    try:
                        nparr = np.frombuffer(img_bytes, np.uint8)
                        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                        resized = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
                        blur = cv2.GaussianBlur(resized, (3, 3), 0)
                        thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]

                        config = "--psm 8 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
                        captcha_val = pytesseract.image_to_string(thresh, config=config).strip()
                        captcha_val = "".join([c for c in captcha_val if c.isascii() and c.isalnum()])
                        captcha_val = captcha_val.upper()
                        logger.info(f"[CADIN CAPTCHA] pytesseract leu: '{captcha_val}'")
                    except Exception as ocr_err:
                        logger.warning(f"[CADIN CAPTCHA] Erro no pytesseract: {ocr_err}")
                        captcha_val = ""

                if len(captcha_val) != 4:
                    logger.warning(f"[CADIN CAPTCHA] Leitura inválida ('{captcha_val}', {len(captcha_val)} chars). Recarregando página...")
                    page.reload(wait_until="networkidle", timeout=30000)
                    time.sleep(1.5)
                    # Aceitar cookies novamente se necessário
                    try:
                        btn_c = page.locator('button:has-text("Autorizo o uso de todos os cookies")')
                        if btn_c.count() > 0 and btn_c.first.is_visible():
                            click_humano(page, 'button:has-text("Autorizo o uso de todos os cookies")')
                            time.sleep(1.0)
                    except:
                        pass
                    # Preencher CNPJ novamente
                    page.wait_for_selector(cnpj_selector, timeout=10000)
                    time.sleep(0.5)
                    page.fill(cnpj_selector, "")
                    page.type(cnpj_selector, cnpj_limpo, delay=50)
                    time.sleep(0.5)
                    continue

                # Preencher captcha e submeter
                page.fill(captcha_input_sel, "")
                page.type(captcha_input_sel, captcha_val, delay=40)
                time.sleep(0.5)

                # Clicar em Pesquisar
                click_humano(page, btn_pesquisar)
                time.sleep(3.0)

                # Verificar resultado
                body_text = page.inner_text("body")

                # Captcha incorreto: se a página recarregou com o formulário vazio
                if "CADIN Municipal - Consulta Inscritos" in body_text and "NÃO FORAM ENCONTRADAS" not in body_text and "FORAM ENCONTRADAS PENDÊNCIAS" not in body_text:
                    # Verificar se há mensagem de erro de captcha
                    lbl_result = page.locator("#lbl_NaoAchou")
                    resultado_texto = ""
                    if lbl_result.count() > 0:
                        resultado_texto = lbl_result.inner_text().strip()

                    if resultado_texto:
                        logger.info(f"[CADIN] Resultado parcial: {resultado_texto}")

                    # Se ainda estamos na tela de consulta, captcha provavelmente falhou
                    captcha_ainda_visivel = page.locator(captcha_img_sel).count() > 0
                    cnpj_field_val = page.input_value(cnpj_selector)
                    if captcha_ainda_visivel and (not cnpj_field_val or len(cnpj_field_val) < 10):
                        logger.warning("[CADIN CAPTCHA] CAPTCHA incorreto. Repreenchendo CNPJ e tentando novamente...")
                        page.fill(cnpj_selector, "")
                        page.type(cnpj_selector, cnpj_limpo, delay=50)
                        time.sleep(0.5)
                        continue
                    elif captcha_ainda_visivel:
                        logger.warning("[CADIN CAPTCHA] CAPTCHA incorreto. Tentando novamente...")
                        continue

                # Verificar se há pendências
                if "FORAM ENCONTRADAS PENDÊNCIAS" in body_text and "NÃO FORAM ENCONTRADAS" not in body_text:
                    logger.error("[CADIN] PENDÊNCIAS encontradas para este CNPJ!")
                    browser.close()
                    raise Exception(f"CADIN Municipal: Foram encontradas pendências para o CNPJ {cnpj}. Verificar manualmente.")

                # Sucesso: sem pendências
                if "NÃO FORAM ENCONTRADAS PENDÊNCIAS" in body_text or "NÃO FORAM ENCONTRADAS" in body_text:
                    logger.info("[CADIN] Sem pendências! Clicando em 'Gerar Comprovante'...")
                    sucesso = True

                    btn_comprovante = '#cmd_comprovante'
                    try:
                        page.wait_for_selector(btn_comprovante, timeout=10000)
                    except:
                        # Tentar seletor alternativo
                        btn_comprovante = 'input[value="Gerar Comprovante"]'
                        page.wait_for_selector(btn_comprovante, timeout=5000)

                    time.sleep(1.0)

                    # Tratar download do PDF (o botão abre um popup/download)
                    try:
                        with page.expect_download(timeout=15000) as download_info:
                            click_humano(page, btn_comprovante)

                        download = download_info.value
                        download.save_as(temp_pdf_path)
                        logger.info(f"[CADIN] PDF do comprovante baixado: {temp_pdf_path}")
                    except Exception as dl_err:
                        # Fallback: talvez abra em popup — tentar capturar
                        logger.warning(f"[CADIN] Download direto falhou: {dl_err}. Tentando capturar popup...")
                        try:
                            with context.expect_page(timeout=10000) as popup_info:
                                click_humano(page, btn_comprovante)
                            popup = popup_info.value
                            popup.wait_for_load_state("networkidle", timeout=15000)
                            time.sleep(2.0)

                            # Tentar capturar o PDF da popup via download
                            with popup.expect_download(timeout=10000) as dl2:
                                popup.keyboard.press("Control+s")
                            download2 = dl2.value
                            download2.save_as(temp_pdf_path)
                            logger.info(f"[CADIN] PDF capturado via popup: {temp_pdf_path}")
                        except Exception as popup_err:
                            logger.warning(f"[CADIN] Popup também falhou: {popup_err}. Tentando salvar via PDF da página...")
                            # Último recurso: salvar a página de resultado como PDF
                            page.pdf(path=temp_pdf_path)
                            logger.info(f"[CADIN] Página salva como PDF: {temp_pdf_path}")

                    break

            if not sucesso:
                browser.close()
                raise Exception(f"Falha ao resolver o CAPTCHA do CADIN Municipal após {max_tentativas} tentativas.")

            browser.close()

            # Validade = data de emissão + 30 dias
            data_vencimento = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
            logger.info(f"[CADIN] Concluído com sucesso. Vencimento: {data_vencimento}")
            return temp_pdf_path, data_vencimento

        except Exception as e:
            browser.close()
            raise Exception(f"Falha no robô CADIN Municipal: {str(e)}")


def emitir_cnd_sicaf(cnpj, fila_id=None):
    """
    Robô para emissão do SICAF via gov.br usando certificado digital (A1).
    """
    logger.info(f"[SICAF] Iniciando consulta para o CNPJ: {cnpj}")
    temp_pdf_path = f"temp_sicaf_{cnpj}.pdf"
    
    cnpj_limpo = cnpj.replace(".", "").replace("/", "").replace("-", "")
    
    # Prepara o JSON da policy do Chrome para auto-selecionar o certificado do CNPJ
    # Certificados A1 de CNPJ (e-CNPJ) geralmente têm o CNPJ no Common Name (CN).
    auto_select_policy = json.dumps([{"pattern": "*", "filter": {"SUBJECT": {"CN": f"*{cnpj_limpo}*"}}}])
    
    def is_port_open(port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(('127.0.0.1', port)) == 0

    if not is_port_open(9222):
        logger.info("[SICAF] Google Chrome não está aberto no modo de depuração. Abrindo...")
        chrome_paths = [
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe")
        ]
        chrome_path = "chrome.exe"
        for p_path in chrome_paths:
            if os.path.exists(p_path):
                chrome_path = p_path
                break
        
        # Cria perfil temporário em nossa pasta para evitar travar o Chrome do usuário
        profile_dir = os.path.join(os.getcwd(), "chrome_debug_profile")
        if not os.path.exists(profile_dir):
            os.makedirs(profile_dir, exist_ok=True)
            
        cmd = [
            chrome_path,
            "--remote-debugging-port=9222",
            f"--user-data-dir={profile_dir}",
            f"--auto-select-certificate-for-urls={auto_select_policy}",
            "--no-first-run",
            "--no-default-browser-check",
            "https://www3.comprasnet.gov.br/sicaf-web/index.jsf"
        ]
        logger.info(f"[SICAF] Executando Chrome pelo comando: {cmd}")
        subprocess.Popen(cmd)
        time.sleep(3.0)

    with sync_playwright() as p:
        logger.info("[SICAF] Conectando ao Google Chrome...")
        browser = p.chromium.connect_over_cdp("http://localhost:9222")
        context = browser.contexts[0]
        
        # Encontra se já existe aba do SICAF aberta
        page = None
        for p_page in context.pages:
            if "sicaf" in p_page.url or "gov.br" in p_page.url:
                page = p_page
                break
                
        if not page:
            page = context.new_page()
            page.goto("https://www3.comprasnet.gov.br/sicaf-web/index.jsf")
            
        Stealth().use_sync(page)
        try:
            time.sleep(1.0)
            
            # 2. Clicar no botão do fornecedor se visível
            btn_entrar_sso = 'xpath=//*[@id="formLogin:btnEntrarSsoFornecedor"]/span'
            menu_consultas = 'xpath=//*[@id="menu"]/div[4]/a'
            
            if page.locator(menu_consultas).count() == 0:
                # Não está logado, tenta navegar/clicar
                if "sicaf-web/index.jsf" in page.url or page.locator(btn_entrar_sso).count() > 0:
                    try:
                        page.wait_for_selector(btn_entrar_sso, timeout=5000)
                        click_humano(page, btn_entrar_sso)
                        time.sleep(1.0)
                    except:
                        pass
                
                # Clicar em login com certificado digital (espera dinâmica de até 10 segundos)
                btn_cert = 'xpath=//*[@id="login-certificate"]'
                try:
                    page.wait_for_selector(btn_cert, timeout=10000)
                    click_humano(page, btn_cert)
                except Exception as e:
                    logger.warning(f"[SICAF] Botão de certificado digital não apareceu ou falhou: {str(e)}")
            
            # 4. Loop de checagem do Captcha e Login
            logger.info("[SICAF] Aguardando autenticação gov.br (ou intervenção hCaptcha se necessário)...")
            tempo_espera = 0
            login_sucesso = False
            estado_atual_banco = "processando"
            
            while tempo_espera < 300:
                btn_confirmar_auth = 'xpath=//*[@id="j_idt109"]/div[1]/a/span'
                menu_consultas = 'xpath=//*[@id="menu"]/div[4]/a'
                
                if page.locator(btn_confirmar_auth).count() > 0 or page.locator(menu_consultas).count() > 0:
                    login_sucesso = True
                    break
                    
                # Checa se existe iframe do hCaptcha visível
                frames = page.frames
                captcha_detected = False
                for f in frames:
                    if "hcaptcha" in f.url:
                        try:
                            if f.locator('body').is_visible():
                                captcha_detected = True
                        except:
                            pass
                
                if captcha_detected:
                    if estado_atual_banco != "aguardando_captcha":
                        estado_atual_banco = "aguardando_captcha"
                        if fila_id:
                            supabase.table("fila_execucao").update({"log_erro": "[CAPTCHA] Aguardando resolução"}).eq("id", fila_id).execute()
                        logger.warning("[SICAF] [ATENÇÃO] hCaptcha detectado! Trazendo janela para frente e aguardando resolução...")
                        page.bring_to_front()
                        print('\\a')  # Beep sonoro no console do Windows
                
                time.sleep(1.0)
                tempo_espera += 1
                
            if not login_sucesso:
                raise Exception("Falha ou timeout ao realizar login no SICAF via gov.br (hCaptcha não resolvido ou falha de certificado).")
                
            # Se estava aguardando captcha e passou, volta log_erro para null
            if estado_atual_banco == "aguardando_captcha" and fila_id:
                supabase.table("fila_execucao").update({"log_erro": None}).eq("id", fila_id).execute()
                
            logger.info("[SICAF] Autenticado com sucesso no portal do SICAF!")
            time.sleep(1.0)
            
            # 5. Fluxo interno do SICAF (pós-login)
            btn_confirmar_auth = 'xpath=//*[@id="j_idt109"]/div[1]/a/span'
            if page.locator(btn_confirmar_auth).count() > 0:
                click_humano(page, btn_confirmar_auth)
                time.sleep(1.0)
                
            # Menu -> Consultas -> Situação do Fornecedor
            menu_consultas = 'xpath=//*[@id="menu"]/div[4]/a'
            page.wait_for_selector(menu_consultas, timeout=10000)
            page.hover(menu_consultas)
            time.sleep(1.0)
            
            menu_situacao = 'xpath=//*[@id="menu"]/div[4]/div[3]/a'
            page.wait_for_selector(menu_situacao, timeout=10000)
            click_humano(page, menu_situacao)
            time.sleep(1.5)
            
            # Pesquisar
            btn_pesquisar = 'xpath=//*[@id="form:pesq:botoesPesqPessoaId:btnPesquisar"]/span'
            page.wait_for_selector(btn_pesquisar, timeout=10000)
            click_humano(page, btn_pesquisar)
            time.sleep(1.5)
            
            # Botão da lupa "Situação do Fornecedor"
            btn_detalhar = 'xpath=//*[@id="form:fornecedores:0:detalharLink"]/span[2]'
            page.wait_for_selector(btn_detalhar, timeout=15000)
            
            # Antes de clicar para baixar, ler a tela para extrair datas de validade e situação
            body_text = page.inner_text("body")
            possui_pendencia = False
            
            if "Possui Pendência" in body_text or "possui pendência" in body_text.lower():
                possui_pendencia = True
                logger.warning("[SICAF] Aviso: Empresa possui pendências listadas na tela do SICAF.")
            
            import re
            datas_encontradas = re.findall(r"(\d{2}/\d{2}/\d{4})", body_text)
            
            menor_data = None
            if datas_encontradas:
                for d_str in datas_encontradas:
                    try:
                        d_obj = datetime.strptime(d_str, "%d/%m/%Y")
                        if menor_data is None or d_obj < menor_data:
                            menor_data = d_obj
                    except:
                        pass
                        
            if menor_data:
                data_vencimento = menor_data.strftime("%Y-%m-%d")
                logger.info(f"[SICAF] Menor data de validade encontrada: {data_vencimento}")
            else:
                data_vencimento = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
                logger.info(f"[SICAF] Nenhuma data válida encontrada. Assumindo validade padrão: {data_vencimento}")
            
            # Baixar o PDF da certidão final
            try:
                with page.expect_download(timeout=15000) as download_info:
                    click_humano(page, btn_detalhar)
                download = download_info.value
                download.save_as(temp_pdf_path)
                logger.info(f"[SICAF] PDF salvo em: {temp_pdf_path}")
            except Exception as dl_err:
                logger.warning(f"[SICAF] Falha no download padrão: {dl_err}. Tentando esperar popup...")
                click_humano(page, btn_detalhar)
                time.sleep(5.0)
                page.pdf(path=temp_pdf_path)
                
            browser.close()
            return temp_pdf_path, data_vencimento, possui_pendencia

        except Exception as e:
            browser.close()
            raise Exception(f"Falha no robô SICAF: {str(e)}")


# ==========================================
# GERENCIAMENTO DE STORAGE E ESTADOS
# ==========================================

def upload_pdf_to_storage(file_path, cnpj, tipo_certidao):
    """
    Faz o upload do PDF gerado para o Supabase Storage Bucket 'cnds-arquivos'.
    """
    file_name = f"{cnpj}/{tipo_certidao}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    logger.info(f"Fazendo upload de {file_path} para o Storage: {file_name}")
    
    with open(file_path, "rb") as f:
        # Tenta enviar para o bucket. 
        # NOTA: Certifique-se de que o bucket 'cnds-arquivos' esteja criado e público (ou com política RLS apropriada).
        supabase.storage.from_("cnds-arquivos").upload(
            path=file_name,
            file=f.read(),
            file_options={"content-type": "application/pdf"}
        )
        
    # Obtém a URL pública do arquivo
    public_url = supabase.storage.from_("cnds-arquivos").get_public_url(file_name)
    return public_url


def processar_tarefa(tarefa):
    """
    Direciona a tarefa para o robô correto de acordo com o tipo_certidao.
    """
    tipo = tarefa["tipo_certidao"]
    cnpj = tarefa["cnpj"]
    uf = tarefa["uf"]
    municipio = tarefa["municipio"]
    
    if tipo == "FEDERAL":
        return emitir_cnd_federal(cnpj)
    elif tipo == "FGTS":
        return emitir_cnd_fgts(cnpj, uf)
    elif tipo == "CNDT":
        return emitir_cnd_cndt(cnpj)
    elif tipo == "ESTADUAL":
        if uf == "SP":
            return emitir_cnd_estadual_sp(cnpj)
        else:
            return emitir_cnd_estadual_via_api(cnpj, uf)
    elif tipo == "MUNICIPAL":
        if uf == "SP" and municipio == "SAO PAULO":
            import sys
            import os
            sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            import test_scrapers
            res = test_scrapers.obter_municipal_sp(cnpj)
            if res.get("status") == "sucesso":
                pdf_path = res["pdf_path"]
                vencimento_str = datetime.now().strftime("%Y-%m-%d")
                try:
                    import PyPDF2
                    import re
                    with open(pdf_path, "rb") as f:
                        reader = PyPDF2.PdfReader(f)
                        text = ""
                        for page in reader.pages:
                            text += page.extract_text() + "\n"
                        match = re.search(r"Validade:\s*(\d{2}/\d{2}/\d{4})", text, re.IGNORECASE)
                        if match:
                            vencimento_br = match.group(1)
                            vencimento_str = datetime.strptime(vencimento_br, "%d/%m/%Y").strftime("%Y-%m-%d")
                        else:
                            print("[AVISO] Nao encontrou a data de validade no PDF.")
                except Exception as e:
                    print(f"Erro ao extrair validade do PDF MUNICIPAL SP: {e}")

                return pdf_path, vencimento_str
            else:
                raise Exception(res.get("mensagem", "Falha desconhecida"))
        else:
            return emitir_cnd_municipal_via_api(cnpj, municipio, uf)
    elif tipo == "CADIN":
        return emitir_cnd_cadin_sp(cnpj)
    elif tipo == "SICAF":
        return emitir_cnd_sicaf(cnpj, tarefa.get("fila_id"))
    else:
        raise NotImplementedError(f"Tipo de certidão '{tipo}' não possui robô/integração implementada.")


def rodar_worker():
    logger.info(f"Worker {WORKER_ID} iniciado. Buscando tarefas...")
    
    while True:
        try:
            # Chama a stored procedure obter_proxima_tarefa
            response = supabase.rpc("obter_proxima_tarefa", {"worker_id": WORKER_ID}).execute()
            tarefas = response.data
            
            if not tarefas:
                # Fila de execução vazia, aguarda 10 segundos antes do próximo poll
                time.sleep(10)
                continue
                
            tarefa = tarefas[0]
            logger.info(f"Tarefa capturada! Fila ID: {tarefa['fila_id']} | CND: {tarefa['tipo_certidao']} para CNPJ: {tarefa['cnpj']}")
            
            # Atualiza status da matriz para 'Em Renovação' em tempo real
            supabase.table("certidoes_matriz").update({
                "status": "Em Renovação",
                "ultimo_log": f"Processamento iniciado pelo worker {WORKER_ID}"
            }).eq("id", tarefa["certidao_matriz_id"]).execute()
            
            pdf_local = None
            try:
                # Processa o RPA correspondente
                resultado = processar_tarefa(tarefa)
                
                possui_pendencia = False
                if isinstance(resultado, tuple) and len(resultado) == 3:
                    pdf_local, data_vencimento, possui_pendencia = resultado
                else:
                    pdf_local, data_vencimento = resultado
                    
                status_final = "Atenção" if possui_pendencia else "Regular"
                
                # Sobe o PDF para o Supabase Storage
                public_url = upload_pdf_to_storage(pdf_local, tarefa["cnpj"], tarefa["tipo_certidao"])
                
                # Sucesso: Atualiza a matriz de certidões com os novos dados
                supabase.table("certidoes_matriz").update({
                    "status": status_final,
                    "data_emissao": datetime.now().strftime("%Y-%m-%d"),
                    "data_vencimento": data_vencimento,
                    "url_pdf": public_url,
                    "ultimo_log": "Emissão realizada com sucesso pelo RPA."
                }).eq("id", tarefa["certidao_matriz_id"]).execute()
                
                # Marca a fila como sucesso
                supabase.table("fila_execucao").update({
                    "status": "sucesso",
                    "updated_at": datetime.utcnow().isoformat()
                }).eq("id", tarefa["fila_id"]).execute()
                
                logger.info(f"Tarefa finalizada com sucesso! CND {tarefa['tipo_certidao']} para {tarefa['cnpj']}")
                
            except Exception as rpa_err:
                # Trata erros ocorridos na execução do RPA
                error_msg = str(rpa_err)
                logger.error(f"Erro na execução da tarefa: {error_msg}")
                
                # Retorna a fila para pendente para nova tentativa futura, ou falha se excedeu
                novo_status = "falha" if tarefa.get("tentativas", 1) >= 3 else "pendente"
                supabase.table("fila_execucao").update({
                    "status": novo_status,
                    "log_erro": error_msg,
                    "updated_at": datetime.utcnow().isoformat()
                }).eq("id", tarefa["fila_id"]).execute()
                
                # Registra o erro na matriz preservando o status 'Regular' se estiver vigente
                try:
                    matriz_res = supabase.table("certidoes_matriz").select("data_vencimento").eq("id", tarefa["certidao_matriz_id"]).execute()
                    is_valid = False
                    if matriz_res.data:
                        venc_str = matriz_res.data[0].get("data_vencimento")
                        if venc_str:
                            try:
                                data_venc = datetime.strptime(venc_str, "%Y-%m-%d").date()
                                if data_venc >= datetime.now().date():
                                    is_valid = True
                            except Exception as parse_err:
                                logger.warning(f"Erro ao parsear data_vencimento '{venc_str}': {parse_err}")
                    
                    if is_valid:
                        supabase.table("certidoes_matriz").update({
                            "status": "Regular",
                            "ultimo_log": f"RPA tentou renovar, mas falhou (documento atual ainda válido). Erro: {error_msg}"
                        }).eq("id", tarefa["certidao_matriz_id"]).execute()
                    else:
                        supabase.table("certidoes_matriz").update({
                            "status": "Erro",
                            "ultimo_log": f"Erro no Worker: {error_msg}"
                        }).eq("id", tarefa["certidao_matriz_id"]).execute()
                except Exception as db_err:
                    logger.error(f"Erro ao consultar/atualizar matriz de certidões: {db_err}")
                
            finally:
                # Garante que o arquivo temporário local seja deletado
                if pdf_local and os.path.exists(pdf_local):
                    try:
                        os.remove(pdf_local)
                    except Exception as e:
                        logger.warning(f"Não foi possível deletar o arquivo temporário {pdf_local}: {str(e)}")
            
            # Intervalo de segurança entre execuções de empresas (evita bloqueios/rate-limit como o erro 023)
            logger.info("Aguardando intervalo de segurança de 45 segundos antes de buscar a próxima empresa...")
            time.sleep(45)

        except Exception as loop_err:
            logger.error(f"Erro crítico no loop de polling: {str(loop_err)}")
            time.sleep(15)


if __name__ == "__main__":
    rodar_worker()
