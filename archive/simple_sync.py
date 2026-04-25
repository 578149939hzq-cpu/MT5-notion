#!/usr/bin/env python3
"""
简化版同步脚本 - 解决Notion数据库权限问题
"""

import os
import sys
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv
import pytz
import time

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('mt5_notion_sync.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 加载环境变量
load_dotenv()

# 配置参数
DATABASE_ID = os.getenv('DATABASE_ID')  # 从环境变量读取，保持灵活性
TIMEZONE = 'Asia/Shanghai'

def check_dependencies():
    """检查依赖库是否安装"""
    required_libs = {
        'MetaTrader5': 'MetaTrader5',
        'notion_client': 'notion_client',
        'dotenv': 'dotenv',
        'pytz': 'pytz',
        'requests': 'requests'
    }

    missing_libs = []
    for lib_name, import_name in required_libs.items():
        try:
            __import__(import_name)
            logger.info(f"[OK] {lib_name} 已安装")
        except ImportError:
            logger.error(f"[ERROR] {lib_name} 未安装")
            missing_libs.append(lib_name)

    if missing_libs:
        raise ImportError(f"缺失依赖库: {', '.join(missing_libs)}")

    logger.info("[OK] 所有依赖库检查通过")

class MT5Connector:
    """MT5 连接器类"""

    def __init__(self):
        self.connected = False

    def connect(self):
        """连接到 MT5"""
        try:
            import MetaTrader5 as mt5

            logger.info("正在连接 MT5...")

            # 从环境变量获取MT5登录信息
            account = os.getenv('MT5_ACCOUNT')
            password = os.getenv('MT5_PASSWORD')
            server = os.getenv('MT5_SERVER')

            # 如果配置了登录信息，尝试自动登录
            if account and password and server:
                logger.info(f"尝试使用账号 {account} 自动登录到服务器 {server}")
                if mt5.initialize(login=int(account), password=password, server=server):
                    self.connected = True
                    logger.info(f"[OK] MT5 自动登录成功")
                    logger.info(f"MT5 版本: {mt5.version()}")
                    return True
                else:
                    logger.error("[ERROR] MT5 自动登录失败，请确保MT5客户端已手动登录")
                    return False
            else:
                # 没有配置登录信息，尝试仅连接
                if mt5.initialize():
                    self.connected = True
                    logger.info(f"[OK] MT5 连接成功")
                    logger.info(f"MT5 版本: {mt5.version()}")
                    return True
                else:
                    logger.error("[ERROR] MT5 连接失败，请确保MT5客户端已手动登录")
                    return False
        except Exception as e:
            logger.error(f"[ERROR] MT5 连接异常: {e}")
            return False

    def disconnect(self):
        """断开 MT5 连接"""
        if self.connected:
            import MetaTrader5 as mt5
            mt5.shutdown()
            self.connected = False
            logger.info("[OK] MT5 连接已断开")

    def get_all_deals(self):
        """获取所有成交记录"""
        if not self.connected:
            logger.error("[ERROR] MT5 未连接")
            return []

        try:
            import MetaTrader5 as mt5

            logger.info("获取所有成交记录...")

            # 获取所有成交记录
            end_time = datetime.now()
            start_time = end_time - timedelta(days=365)
            start_timestamp = int(start_time.timestamp())
            end_timestamp = int(end_time.timestamp())

            deals = mt5.history_deals_get(start_timestamp, end_timestamp)

            if deals is None:
                logger.warning("[WARNING] 获取成交记录失败")
                return []

            logger.info(f"获取到 {len(deals)} 条成交记录")

            # 过滤：只保留平仓单和有用的挂单
            closed_deals = [deal for deal in deals if deal.entry == 2]  # 平仓单
            entry_in_deals = [deal for deal in deals if deal.entry == 0 and deal.volume > 0]  # 有仓位的挂单

            logger.info(f"成交记录总数: {len(deals)}")
            logger.info(f"平仓单数量: {len(closed_deals)}")
            logger.info(f"有效挂单数量: {len(entry_in_deals)}")

            # 优先返回平仓单，如果没有则返回挂单
            if closed_deals:
                selected_deals = closed_deals
                deal_type = "平仓单"
            elif entry_in_deals:
                selected_deals = entry_in_deals
                deal_type = "挂单"
            else:
                selected_deals = []
                deal_type = "无有效记录"

            logger.info(f"准备同步 {len(selected_deals)} 条{deal_type}记录")

            if selected_deals:
                # 显示第一条记录作为示例
                example = selected_deals[0]
                logger.info("示例数据:")
                logger.info(f"  订单ID: {example.ticket}")
                logger.info(f"  交易标的: {example.symbol}")
                logger.info(f"  交易类型: {'买入' if example.type == 0 else '卖出'}")
                logger.info(f"  时间: {datetime.fromtimestamp(example.time)}")
            else:
                logger.info("[WARNING] 没有找到有效的交易记录")

            return selected_deals

        except Exception as e:
            logger.error(f"[ERROR] 获取成交记录失败: {e}")
            return []

class NotionSync:
    """Notion 同步器类"""

    def __init__(self):
        self.token = os.getenv('NOTION_TOKEN')
        self.database_id = os.getenv('DATABASE_ID')
        self.client = None

    def connect(self):
        """连接到 Notion"""
        try:
            from notion_client import Client

            if not self.token:
                raise ValueError("NOTION_TOKEN 未设置")

            if not self.database_id:
                raise ValueError("DATABASE_ID 未设置")

            logger.info(f"正在连接 Notion...")
            logger.info(f"数据库ID: {self.database_id}")

            self.client = Client(auth=self.token)
            logger.info("[OK] Notion 连接成功")

            return True
        except Exception as e:
            logger.error(f"[ERROR] Notion 连接失败: {e}")
            return False

    def format_deal_to_notion(self, deal):
        """将 MT5 成交记录格式化为 Notion 数据格式"""
        # 转换交易方向
        direction = '多' if deal.type == 0 else '空'

        # 转换时间（MT5 时间戳 -> UTC+8）
        deal_time = datetime.fromtimestamp(deal.time)
        utc8_timezone = pytz.timezone(TIMEZONE)
        deal_time_utc8 = deal_time.astimezone(utc8_timezone)

        # 格式化日期
        date_str = deal_time_utc8.strftime('%Y-%m-%d')

        # 处理价格字段
        price_open = getattr(deal, 'price_open', None)
        price_close = getattr(deal, 'price_close', None)
        sl = getattr(deal, 'sl', 0)
        tp = getattr(deal, 'tp', 0)

        # 创建 Notion 数据结构
        notion_data = {
            "parent": {
                "database_id": self.database_id
            },
            "properties": {
                "交易标的": {
                    "title": [
                        {
                            "text": {
                                "content": deal.symbol
                            }
                        }
                    ]
                },
                "方向": {
                    "select": {
                        "name": direction
                    }
                },
                "交易日期": {
                    "date": {
                        "start": date_str,
                        "end": None
                    }
                },
                "入场价格": {
                    "number": price_open
                },
                "实际出场价格": {
                    "number": price_close
                },
                "止损": {
                    "number": sl if sl > 0 else None
                },
                "止盈": {
                    "number": tp if tp > 0 else None
                },
                "仓位": {
                    "number": deal.volume
                },
                "订单ID": {
                    "rich_text": [
                        {
                            "text": {
                                "content": str(deal.ticket)
                            }
                        }
                    ]
                }
            }
        }

        return notion_data

    def sync_deal(self, deal):
        """同步单个成交记录到 Notion"""
        try:
            # 格式化数据
            notion_data = self.format_deal_to_notion(deal)

            # 添加到数据库
            response = self.client.pages.create(**notion_data)

            logger.info(f"[OK] 成功同步订单 ID: {deal.ticket}")
            return True
        except Exception as e:
            logger.error(f"[ERROR] 同步订单 {deal.ticket} 失败: {e}")
            return False

    def sync_deals(self, deals):
        """批量同步成交记录到 Notion"""
        if not self.client:
            logger.error("[ERROR] Notion 未连接")
            return 0, 0

        success_count = 0
        skip_count = 0

        logger.info(f"开始同步 {len(deals)} 条成交记录...")

        for i, deal in enumerate(deals, 1):
            logger.info(f"正在处理第 {i}/{len(deals)} 条记录...")

            if self.sync_deal(deal):
                success_count += 1
            else:
                skip_count += 1

            # 添加延迟，避免 API 限制
            if i < len(deals):
                time.sleep(0.5)

        logger.info("=" * 50)
        logger.info("同步完成!")
        logger.info(f"成功同步: {success_count} 条")
        logger.info(f"失败: {skip_count} 条")
        logger.info("=" * 50)

        return success_count, skip_count

def main():
    """主函数"""
    logger.info("MT5 到 Notion 交易数据同步开始（简化版）")
    logger.info("=" * 50)

    # 检查依赖
    try:
        check_dependencies()
    except ImportError as e:
        logger.error(str(e))
        sys.exit(1)

    # 检查环境变量
    if not os.getenv('NOTION_TOKEN'):
        logger.error("[ERROR] 请在 .env 文件中设置 NOTION_TOKEN")
        sys.exit(1)

    if not os.getenv('DATABASE_ID'):
        logger.error("[ERROR] 请在 .env 文件中设置 DATABASE_ID")
        sys.exit(1)

    # 初始化连接器
    mt5_connector = MT5Connector()
    notion_sync = NotionSync()

    try:
        # 连接 MT5
        if not mt5_connector.connect():
            logger.error("[ERROR] 无法连接到 MT5")
            sys.exit(1)

        # 连接 Notion
        if not notion_sync.connect():
            logger.error("[ERROR] 无法连接到 Notion")
            sys.exit(1)

        # 获取 MT5 数据
        logger.info("正在获取所有交易数据...")
        deals = mt5_connector.get_all_deals()

        if not deals:
            logger.info("[INFO] 没有需要同步的成交记录")
            return

        # 同步到 Notion
        success_count, skip_count = notion_sync.sync_deals(deals)

        logger.info(f"本次同步完成！新增记录: {success_count}, 失败: {skip_count}")

    except KeyboardInterrupt:
        logger.info("\n用户中断操作")
    except Exception as e:
        logger.error(f"[ERROR] 程序异常: {e}")
        sys.exit(1)
    finally:
        # 断开 MT5 连接
        mt5_connector.disconnect()
        logger.info("程序结束")

if __name__ == "__main__":
    main()