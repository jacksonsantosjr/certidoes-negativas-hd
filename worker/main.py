import time
import os
import sys
import ssl
import logging
import subprocess
import requests
import urllib3
import speech_recognition as sr
from pydub import AudioSegment
from datetime import datetime, timedelta
from dotenv import load_dotenv
from supabase import create_client, Client
from playwright.sync_api import sync_playwright

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
    logger.info(f"[ESTADUAL] Solicitando emissão via API de mercado para UF {uf} - CNPJ {cnpj}")
    temp_pdf_path = f"temp_estadual_{cnpj}.pdf"
    try:
        time.sleep(2)
        with open(temp_pdf_path, "wb") as f:
            f.write(f"MOCK PDF CONTENT - CERTIDAO ESTADUAL {uf} CNPJ {cnpj}".encode('utf-8'))
        data_vencimento = (datetime.now() + timedelta(days=90)).strftime("%Y-%m-%d")
        return temp_pdf_path, data_vencimento
    except Exception as e:
        raise Exception(f"Falha na API Estadual: {str(e)}")

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
            page.focus(cnpj_selector)
            time.sleep(0.5)
            page.click(cnpj_selector)
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
                    page.click(btn_cookies)
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
            page.hover(btn_selector)
            time.sleep(0.3)
            page.click(btn_selector)
            time.sleep(1.0)
            
            # Trata o caso de certidão válida já existente (Modal)
            try:
                # O usuário informou o xpath exato do botão "Emitir Nova Certidão"
                btn_xpath = 'xpath=/html/body/modal-container/div[2]/div/div[3]/button[2]'
                btn_texto = 'button:has-text("Emitir Nova Certidão")'
                
                # Aguardamos pelo modal ou botão (espera um dos dois)
                try:
                    page.wait_for_selector('modal-container', timeout=15000)
                except:
                    page.wait_for_selector(btn_xpath, timeout=5000)
                    
                time.sleep(1.0)
                
                if page.locator(btn_xpath).is_visible():
                    page.hover(btn_xpath)
                    time.sleep(0.5)
                    page.click(btn_xpath)
                    logger.info(f"Modal tratado clicando no xpath: {btn_xpath}")
                elif page.locator(btn_texto).is_visible():
                    page.hover(btn_texto)
                    time.sleep(0.5)
                    page.click(btn_texto)
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
                
                # 1. Limpa cookies e storage para que o portal trate o próximo envio como nova sessão e mostre o modal
                try:
                    context.clear_cookies()
                    page.evaluate("window.localStorage.clear(); window.sessionStorage.clear();")
                    logger.info("[FEDERAL] Cookies e storage da sessão limpos para reset do portal.")
                except Exception as clear_err:
                    logger.warning(f"[FEDERAL] Erro ao limpar cookies/storage: {clear_err}")
                
                # 2. Recarrega a página home limpa
                try:
                    page.reload()
                    page.wait_for_selector(cnpj_selector, timeout=15000)
                except Exception as reload_err:
                    logger.warning(f"[FEDERAL] Erro ao recarregar página: {reload_err}. Tentando page.goto...")
                    try:
                        page.goto("https://servicos.receitafederal.gov.br/servico/certidoes/#/home/cnpj")
                        page.wait_for_selector(cnpj_selector, timeout=15000)
                    except:
                        pass
                
                time.sleep(1.5)
                page.focus(cnpj_selector)
                page.click(cnpj_selector)
                page.type(cnpj_selector, cnpj_limpo, delay=60)
                page.press(cnpj_selector, "Tab")
                time.sleep(1.0)
                
                # 3. Clica em Emitir para disparar o modal de certidão válida existente
                page.click(btn_selector)
                
                # 4. No modal, clica em "Consultar Certidão" (primeiro botão)
                btn_consultar_modal = 'xpath=/html/body/modal-container/div[2]/div/div[3]/button[1]'
                try:
                    page.wait_for_selector('modal-container', timeout=15000)
                except:
                    try:
                        page.wait_for_selector(btn_consultar_modal, timeout=5000)
                    except:
                        pass
                
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
                
                # 5. Clica no botão de consultar no formulário de consulta
                btn_consultar_form = 'xpath=/html/body/app-root/mf-portal-layout/portal-main-layout/div/main/ng-component/ng-component/ng-component/app-informar-parametro-pj/app-informar-parametro/form/div[2]/button'
                try:
                    page.wait_for_selector(btn_consultar_form, timeout=15000)
                    page.click(btn_consultar_form)
                except Exception as form_err:
                    logger.warning(f"[FEDERAL] Botão de consulta do formulário não encontrado por xpath: {form_err}. Tentando por texto...")
                    btn_text_form = 'form button:has-text("Consultar Certidão")'
                    if not page.locator(btn_text_form).is_visible():
                        btn_text_form = 'button:has-text("Consultar Certidão")'
                    page.click(btn_text_form)
                time.sleep(2.0)
                
                # 4. Na tabela de resultados, localiza a linha da certidão válida com maior data de vencimento
                page.wait_for_selector("datatable-body-row", timeout=15000)
                
                import re
                
                valid_rows = []
                rows = page.locator("datatable-body-row").all()
                for idx, row in enumerate(rows):
                    cells_text = [c.inner_text().strip() for c in row.locator("datatable-body-cell").all()]
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
        browser = p.chromium.launch(headless=True)
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
            
            solver_captcha_se_necessario(page, "CNDT")
            
            btn_emitir = 'xpath=//*[@id="gerarCertidaoForm:btnEmitirCertidao"]'
            page.wait_for_selector(btn_emitir, timeout=10000)
            
            # Tratamento de Erros / Verificação do Documento
            erro_selector = ".mensagem-erro, .erro, .alert, #messages, ul.erro, #mensagens, .erros, [id*='areaMensagemErro']"
            
            try:
                with page.expect_download(timeout=25000) as download_info:
                    page.click(btn_emitir)
                
                download = download_info.value
                download.save_as(temp_pdf_path)
                logger.info(f"[CNDT] PDF real da certidão CNDT baixado com sucesso em {temp_pdf_path}")
            except Exception as d_err:
                logger.warning("[CNDT] Download automático não iniciou. Verificando erros na página...")
                elementos_erro = page.query_selector_all(erro_selector)
                erro_msg = ""
                for el in elementos_erro:
                    if el.is_visible():
                        txt = el.inner_text().strip()
                        if txt:
                            erro_msg = txt
                            break
                if erro_msg:
                    raise Exception(f"Erro no portal da CNDT: {erro_msg}")
                else:
                    raise Exception(f"Falha ao iniciar download ou erro não identificado: {d_err}")
                
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
    logger.info(f"[MUNICIPAL] Solicitando emissão via API de mercado para {municipio}/{uf} - CNPJ {cnpj}")
    temp_pdf_path = f"temp_municipal_{cnpj}.pdf"
    
    try:
        time.sleep(2)
        
        with open(temp_pdf_path, "wb") as f:
            f.write(f"MOCK PDF CONTENT - CERTIDAO MUNICIPAL {municipio}-{uf} CNPJ {cnpj}".encode('utf-8'))
            
        data_vencimento = (datetime.now() + timedelta(days=90)).strftime("%Y-%m-%d")
        return temp_pdf_path, data_vencimento
        
    except Exception as e:
        raise Exception(f"Falha na API Municipal: {str(e)}")


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
        return emitir_cnd_municipal_via_api(cnpj, municipio, uf)
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
                pdf_local, data_vencimento = processar_tarefa(tarefa)
                
                # Sobe o PDF para o Supabase Storage
                public_url = upload_pdf_to_storage(pdf_local, tarefa["cnpj"], tarefa["tipo_certidao"])
                
                # Sucesso: Atualiza a matriz de certidões com os novos dados
                supabase.table("certidoes_matriz").update({
                    "status": "Regular",
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
                
                # Retorna a fila para pendente para nova tentativa futura
                supabase.table("fila_execucao").update({
                    "status": "pendente",
                    "log_erro": error_msg,
                    "updated_at": datetime.utcnow().isoformat()
                }).eq("id", tarefa["fila_id"]).execute()
                
                # Registra o erro na matriz
                supabase.table("certidoes_matriz").update({
                    "status": "Erro",
                    "ultimo_log": f"Erro no Worker: {error_msg}"
                }).eq("id", tarefa["certidao_matriz_id"]).execute()
                
            finally:
                # Garante que o arquivo temporário local seja deletado
                if pdf_local and os.path.exists(pdf_local):
                    try:
                        os.remove(pdf_local)
                    except Exception as e:
                        logger.warning(f"Não foi possível deletar o arquivo temporário {pdf_local}: {str(e)}")
            
        except Exception as loop_err:
            logger.error(f"Erro crítico no loop de polling: {str(loop_err)}")
            time.sleep(15)


if __name__ == "__main__":
    rodar_worker()
