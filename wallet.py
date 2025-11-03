from playwright.sync_api import sync_playwright, Page
import os
import json
import dotenv

dotenv.load_dotenv()

EXTENSION_PATH = os.path.join(os.path.dirname(__file__), "plugin/metamask-chrome-12.16.0")  # 解压的插件目录
USER_DATA_DIR = os.path.join(os.path.dirname(__file__), "tmp")  # 持久化上下文
METAMASK_EXTENSION_ID_FILE = os.path.join(os.path.dirname(__file__), "tmp", "metamask_extension_id.txt")
METAMASK_EXTENSION_ID = None

# if exists, read it
if os.path.exists(METAMASK_EXTENSION_ID_FILE):
    with open(METAMASK_EXTENSION_ID_FILE, "r") as f:
        METAMASK_EXTENSION_ID = f.read()

# SEED_PHRASE = kms_get_wallet_words(os.getenv("KMS_PROJECT_ID"))
SEED_PHRASE = os.getenv("SEED_PHRASE")
PASSWORD = os.getenv("METAMASK_WALLET_PASSWORD")
CO_CHAT_URL = os.getenv("CO_CHAT_URL", "https://chat.chainopera.ai/")


def setup_browser(headless: bool = False):
    """Setup Playwright browser"""
    print("🌐 Setting up browser...")
    
    playwright = sync_playwright().start()
    args = [
        # '--no-sandbox', 
        # '--disable-dev-shm-usage', 
        f"--disable-extensions-except={EXTENSION_PATH}",
        f"--load-extension={EXTENSION_PATH}"
    ]
    # check if wallet.EXTENSION_PATH exists
    if not os.path.exists(EXTENSION_PATH):
        raise Exception(f"Extension path directory does not exist: {EXTENSION_PATH}")
    if headless:
        args.append("--headless=new")
    browser = playwright.chromium.launch_persistent_context(
        user_data_dir=None,
        headless=False,
        args=args
    )
    print("✅ Browser ready")
    return browser


def login_metamask(page: Page):
    page.goto("chrome://extensions/") # playwright 需要打开插件页面
    page.wait_for_load_state()
    global METAMASK_EXTENSION_ID
    if not METAMASK_EXTENSION_ID:
        METAMASK_EXTENSION_ID = page.evaluate("""() => {
            const extensions = document.querySelector('extensions-manager').shadowRoot
                .querySelector('extensions-item-list').shadowRoot
                .querySelectorAll('extensions-item');
            for (const extension of extensions) {
                const name = extension.shadowRoot.querySelector('#name').textContent;
                if (name.includes('MetaMask')) {
                    return extension.getAttribute('id');
                }
            }
            return null;
        }""")
        
    if not METAMASK_EXTENSION_ID:
        raise Exception("无法找到MetaMask扩展ID")
    
    with open(os.path.join(os.path.dirname(__file__), "tmp", "metamask_extension_id.txt"), "w") as f:
        f.write(METAMASK_EXTENSION_ID)
    
    # 打开MetaMask扩展页面
    page.goto(f"chrome-extension://{METAMASK_EXTENSION_ID}/home.html")   
    page.get_by_test_id("onboarding-terms-checkbox").click()
    page.get_by_test_id("onboarding-import-wallet").click()
    page.wait_for_load_state()
    page.get_by_test_id("metametrics-i-agree").click()
    page.wait_for_load_state()
    phase_words = SEED_PHRASE.split()
    for i, word in enumerate(phase_words):
        page.get_by_test_id(f"import-srp__srp-word-{i}").fill(word)
    page.get_by_test_id("import-srp-confirm").click()
    page.get_by_test_id("create-password-new").fill(PASSWORD)
    page.get_by_test_id("create-password-confirm").fill(PASSWORD)
    page.get_by_test_id("create-password-terms").click()
    page.get_by_test_id("create-password-import").click()
    page.wait_for_load_state()
    page.get_by_test_id("onboarding-complete-done").click()
    page.get_by_test_id("pin-extension-next").click()
    page.get_by_test_id("pin-extension-done").click()
    page.wait_for_load_state()

    # page.get_by_text("Password").nth(0).fill(PASSWORD)
    # page.get_by_text("Unlock").click()

    MetaMaskPlugin.enable_mainnet(page, "Binance Smart Chain")

    return page


def login_co_chat_page(page: Page):
    co_page = page.context.new_page()
    # print(f"CO_CHAT_URL: {CO_CHAT_URL}")
    co_page.goto(CO_CHAT_URL, timeout=180000)
    co_page.wait_for_load_state()

    try:
        co_page.get_by_role("button", name="Login").click()
    except Exception as e:
        print("没有出现 login 按钮，判断为已经登录")
    else:
        co_page.get_by_text("metamask").click()
        # 等待 MetaMask 弹窗并授权连接
        # popup: Page = context.wait_for_event("page", timeout=2000)  # 弹出 MetaMask 授权窗口
        popup = page.context.new_page()  # 由于无头模式检测不到插件弹窗, 所以改为主动打开插件页面
        popup.goto(f"chrome-extension://{METAMASK_EXTENSION_ID}/home.html") 
        popup.wait_for_load_state()
        popup.get_by_test_id("confirm-btn").click()
        popup.wait_for_load_state()
        popup.get_by_test_id("confirm-footer-button").click()
        popup.close()

    co_page.wait_for_load_state()
    co_page.wait_for_timeout(5000)

    MetaMaskPlugin.add_all_permissions(co_page)

    # get user info from local storage
    user_info = json.loads(co_page.evaluate("""() => {
        return localStorage.getItem('app-user-info');
    }"""))
    # print(f"User Info: {user_info}")

    # save user info to file
    if not os.path.exists(f"{USER_DATA_DIR}"):
        os.makedirs(f"{USER_DATA_DIR}")
    with open(f"{USER_DATA_DIR}/user_info.json", "w") as f:
        json.dump(user_info,f)
    return co_page


class MetaMaskPlugin:
    MSG_PREFIX = 'MetaMask Plugin'

    @staticmethod
    def enable_mainnet(page: Page, mainnet_name: str):
        page.get_by_test_id('network-display').click()
        if not page.get_by_text(mainnet_name).is_visible():
            raise Exception(f"{MetaMaskPlugin.MSG_PREFIX} enable_mainnet 钱包没有找到 {mainnet_name}")
        page.get_by_text(mainnet_name).click()
        page.wait_for_load_state()

        # a list of div contains class 'new-network-list__list-of-networks'
        list_of_networks = page.locator('.new-network-list__list-of-networks').all()
        for network in list_of_networks:
            if network.get_by_text(mainnet_name).is_visible():
                network.get_by_role("button").click()
                page.wait_for_load_state()
                break
        page.get_by_test_id('confirmation-submit-button').click()


    @staticmethod
    def add_all_permissions(page: Page):
        metamask_page = page.context.new_page()
        metamask_page.goto(f"chrome-extension://{METAMASK_EXTENSION_ID}/home.html")
        metamask_page.wait_for_load_state()
        metamask_page.get_by_test_id('account-options-menu-button').click()
        metamask_page.get_by_test_id('global-menu-connected-sites').click()
        metamask_page.get_by_test_id('connection-list-item').click()
        metamask_page.get_by_test_id('edit').last.click()
        metamask_page.get_by_role('checkbox').first.click()
        metamask_page.get_by_test_id('connect-more-chains-button').click()
        metamask_page.close()


    @staticmethod
    def swap_confirm(page: Page):
        page.wait_for_timeout(5000)

        msg_prefix = f"{MetaMaskPlugin.MSG_PREFIX} swap_confirm 钱包签名失败: "
        popup = page.context.new_page()  # 由于无头模式检测不到插件弹窗, 所以改为主动打开插件页面
        popup.goto(f"chrome-extension://{METAMASK_EXTENSION_ID}/home.html") 
        popup.wait_for_load_state('domcontentloaded')
        popup.wait_for_timeout(2000)

        # 余额不足
        if popup.get_by_text('Review alert').is_visible():
            raise Exception(f"{msg_prefix} Review alert")
        
        popup.wait_for_load_state()
        popup.get_by_test_id("okd-button").click()
        popup.wait_for_load_state()
        popup.get_by_test_id("okd-button").click()
        popup.close()


def main():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=None,
            headless=False,
            args=[
                f"--disable-extensions-except={EXTENSION_PATH}",
                f"--load-extension={EXTENSION_PATH}",
                "--headless=haha~"
            ],
        )

        # 获取MetaMask扩展ID
        page = context.pages[0]
        login_metamask(page)
        login_co_chat_page(page)


if __name__ == "__main__":
    main()