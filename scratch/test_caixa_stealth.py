from playwright.sync_api import sync_playwright

def test_caixa_stealth():
    cnpj = "09440233000180"
    uf = "SP"
    print("Testando Caixa FGTS em modo Headless com injeções Stealth...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Use a realistic context with user agent and extra options
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            device_scale_factor=1,
            locale="pt-BR",
            timezone_id="America/Sao_Paulo"
        )
        
        # Inject stealth properties
        context.add_init_script("""
            // Overwrite the `webdriver` property to false
            Object.defineProperty(navigator, 'webdriver', {
                get: () => false
            });
            // Overwrite languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['pt-BR', 'pt', 'en-US', 'en']
            });
            // Mock plugins
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            // Mock chrome object
            window.chrome = {
                runtime: {}
            };
        """)
        
        page = context.new_page()
        
        try:
            url = "https://consulta-crf.caixa.gov.br/consultacrf/pages/consultaEmpregador.jsf"
            print(f"Navegando para {url}")
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            
            cnpj_selector = 'xpath=//*[@id="mainForm:txtInscricao1"]'
            print("Aguardando o campo CNPJ...")
            page.wait_for_selector(cnpj_selector, timeout=20000)
            print("Sucesso! O campo CNPJ foi localizado no modo Headless Stealth.")
            
            cnpj_limpo = cnpj.replace(".", "").replace("/", "").replace("-", "")
            page.fill(cnpj_selector, cnpj_limpo)
            
            uf_selector = 'xpath=//*[@id="mainForm:uf"]'
            page.wait_for_selector(uf_selector, timeout=10000)
            page.select_option(uf_selector, value=uf)
            print("Campos preenchidos.")
            
            btn_selector = 'xpath=//*[@id="mainForm:btnConsultar"]'
            page.click(btn_selector)
            print("Consulta enviada. Aguardando resposta...")
            
            # Wait for response
            sucesso_selector = '[id="mainForm:j_id76"]'
            erro_selector = ".msgErro, .erro, [id='mainForm:mensagens']"
            page.wait_for_selector(f"{sucesso_selector}, {erro_selector}", timeout=25000)
            print("Sucesso! A página respondeu.")
            
            if page.query_selector(sucesso_selector):
                print("Empresa regular no FGTS. Navegando para o CRF...")
                page.click(sucesso_selector)
                
                btn_visualizar = '[id="mainForm:btnVisualizar"]'
                page.wait_for_selector(btn_visualizar, timeout=15000)
                print("Certidão carregada no modo Headless Stealth!")
            else:
                print("Retornou erro:", page.locator(erro_selector).inner_text().strip())
                
        except Exception as e:
            print(f"Erro no modo Headless Stealth: {e}")
            screenshot_path = "caixa_stealth_error.png"
            page.screenshot(path=screenshot_path)
            print(f"Screenshot salvo em '{screenshot_path}'")
        finally:
            browser.close()

if __name__ == "__main__":
    test_caixa_stealth()
