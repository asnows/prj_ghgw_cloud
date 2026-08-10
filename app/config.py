"""配置加载：环境变量 + .env 文件。"""
import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


@lru_cache
def get_settings():
    return Settings()


class Settings:
    """集中配置。生产环境请通过环境变量注入（勿入库）。"""

    # 服务
    APP_ENV: str = os.getenv("APP_ENV", "dev")
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))

    # 数据库
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./ghgw_cloud.db")

    # 签名密钥
    LICENSE_SECRET: str = os.getenv("LICENSE_SECRET", "CHANGE_ME_GENERATE_WITH_GEN_KEYS")

    # 微信支付
    WXPAY_ENABLED: bool = os.getenv("WXPAY_ENABLED", "false").lower() == "true"
    WXPAY_MCHID: str = os.getenv("WXPAY_MCHID", "")
    WXPAY_APPID: str = os.getenv("WXPAY_APPID", "")
    WXPAY_APIV3_KEY: str = os.getenv("WXPAY_APIV3_KEY", "")
    WXPAY_SERIAL_NO: str = os.getenv("WXPAY_SERIAL_NO", "")
    WXPAY_PRIVATE_KEY_PATH: str = os.getenv("WXPAY_PRIVATE_KEY_PATH", "")
    WXPAY_NOTIFY_URL: str = os.getenv("WXPAY_NOTIFY_URL", "")

    # 套餐
    PLAN_MONTH_DAYS: int = int(os.getenv("PLAN_MONTH_DAYS", "30"))
    PLAN_YEAR_DAYS: int = int(os.getenv("PLAN_YEAR_DAYS", "365"))
    PLAN_MONTH_PRICE: int = int(os.getenv("PLAN_MONTH_PRICE", "2900"))  # 分
    PLAN_YEAR_PRICE: int = int(os.getenv("PLAN_YEAR_PRICE", "19900"))

    # 设备绑定上限
    MAX_DEVICES_PER_LICENSE: int = int(os.getenv("MAX_DEVICES_PER_LICENSE", "3"))

    # 管理后台
    ADMIN_TOKEN: str = os.getenv("ADMIN_TOKEN", "CHANGE_ME_ADMIN")

    # skill 分析引擎路径
    SKILL_DIR: str = os.getenv("SKILL_DIR", "/sandbox/workspace/skills/gu-hai-guai-wu")

    # 套餐映射（商品描述 -> 天数；用于 Webhook 回调解读）
    @property
    def plans(self):
        return {
            "month": {"days": self.PLAN_MONTH_DAYS, "price": self.PLAN_MONTH_PRICE, "name": "月卡"},
            "year": {"days": self.PLAN_YEAR_DAYS, "price": self.PLAN_YEAR_PRICE, "name": "年卡"},
        }
