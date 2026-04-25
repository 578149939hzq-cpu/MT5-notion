#!/usr/bin/env python3
"""
智能同步脚本 - 自动适应Notion数据库属性结构
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
DATABASE_ID = os.getenv('DATABASE_ID')
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

            account = os.getenv('MT5_ACCOUNT')
            password = os.getenv('MT5_PASSWORD')
            server = os.getenv('MT5_SERVER')

            if account and password and server:
                logger.info(f"尝试使用账号 {account} 自动登录到服务器 {server}")
                if mt5.initialize(login=int(account), password=password, server=server):
                    self.connected = True
                    logger.info(f"[OK] MT5 自动登录成功")
                    logger.info(f"MT5 版本: {mt5.version()}")
                    return True
                else:
                    logger.error("[ERROR] MT5 自动登录失败")
                    return False
            else:
                if mt5.initialize():
                    self.connected = True
                    logger.info(f"[OK] MT5 连接成功")
                    logger.info(f"MT5 版本: {mt5.version()}")
                    return True
                else:
                    logger.error("[ERROR] MT5 连接失败")
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
            closed_deals = [deal for deal in deals if deal.entry == 2]
            entry_in_deals = [deal for deal in deals if deal.entry == 0 and deal.volume > 0]

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
        self.database_id = DATABASE_ID
        self.client = None
        self.properties_config = {}

    def connect(self):
        """连接到 Notion"""
        try:
            from notion_client import Client

            if not self.token:
                raise ValueError("NOTION_TOKEN 未设置")

            if not self.database_id:
                raise ValueError("DATABASE_ID 未设置")

            logger.info("正在连接 Notion...")
            self.client = Client(auth=self.token)
            logger.info("[OK] Notion 连接成功")

            # 获取数据库结构
            self.analyze_database_structure()

            return True
        except Exception as e:
            logger.error(f"[ERROR] Notion 连接失败: {e}")
            return False

    def analyze_database_structure(self):
        """分析数据库结构并提取属性名称"""
        try:
            db_info = self.client.databases.retrieve(database_id=self.database_id)
            properties = db_info.get('properties', {})

            if not properties:
                logger.error("[ERROR] 数据库是空的，没有定义任何属性")
                logger.info("请先在Notion中为数据库添加属性：")
                logger.info("1. 交易标的 (Title)")
                logger.info("2. 方向 (Select)")
                logger.info("3. 交易日期 (Date)")
                logger.info("4. 入场价格 (Number)")
                logger.info("5. 实际出场价格 (Number)")
                logger.info("6. 止损 (Number)")
                logger.info("7. 止盈 (Number)")
                logger.info("8. 仓位 (Number)")
                logger.info("9. 订单ID (Number/Text)")
                return False

            # 自动检测属性名称
            logger.info("检测到的数据库属性:")
            for prop_name, prop_config in properties.items():
                prop_type = prop_config.get('type', 'unknown')
                logger.info(f"  {prop_name}: {prop_type}")
                self.properties_config[prop_name] = prop_type

            return True

        except Exception as e:
            logger.error(f"[ERROR] 分析数据库结构失败: {e}")
            return False

    def find_property_by_name(self, possible_names):
        """根据可能的中文名称查找属性"""
        for prop_name in self.properties_config.keys():
            for name in possible_names:
                if name.lower() in prop_name.lower():
                    return prop_name, self.properties_config[prop_name]
        return None, None

    def format_deal_to_notion(self, deal):
        """智能格式化数据到Notion"""
        # 定义字段映射
        field_mappings = {
            '交易标的': ['交易标的', 'symbol', '标的', '名称', 'name'],
            '方向': ['方向', 'type', '多空', 'buy_sell'],
            '交易日期': ['交易日期', 'date', 'time', '时间', '日期'],
            '入场价格': ['入场价格', 'entry_price', 'open_price', 'price_open'],
            '实际出场价格': ['实际出场价格', 'exit_price', 'close_price', 'price_close'],
            '止损': ['止损', 'stop_loss', 'sl'],
            '止盈': ['止盈', 'take_profit', 'tp'],
            '仓位': ['仓位', 'volume', 'lots', '手数'],
            '订单ID': ['订单ID', 'ticket', 'order_id', '订单号']
        }

        # 转换交易方向
        direction = '多' if deal.type == 0 else '空'

        # 转换时间
        deal_time = datetime.fromtimestamp(deal.time)
        utc8_timezone = pytz.timezone(TIMEZONE)
        deal_time_utc8 = deal_time.astimezone(utc8_timezone)
        date_str = deal_time_utc8.strftime('%Y-%m-%d')

        # 获取属性名称和类型
        properties = {}

        # 处理每个字段
        for target_field, possible_names in field_mappings.items():
            prop_name, prop_type = self.find_property_by_name(possible_names)

            if not prop_name:
                logger.warning(f"[WARNING] 未找到属性: {target_field} (尝试: {possible_names})")
                continue

            # 根据属性类型设置值
            if target_field == '交易标的':
                properties[prop_name] = {
                    "title": [{"text": {"content": deal.symbol}}]
                }
            elif target_field == '方向':
                properties[prop_name] = {
                    "select": {"name": direction}
                }
            elif target_field == '交易日期':
                properties[prop_name] = {
                    "date": {"start": date_str, "end": None}
                }
            elif target_field in ['入场价格', '实际出场价格', '止损', '止盈']:
                value = None
                if target_field == '入场价格':
                    value = getattr(deal, 'price_open', None)
                elif target_field == '实际出场价格':
                    value = getattr(deal, 'price_close', None)
                elif target_field == '止损':
                    value = getattr(deal, 'sl', 0)
                elif target_field == '止盈':
                    value = getattr(deal, 'tp', 0)

                if value and value > 0:
                    properties[prop_name] = {"number": value}
            elif target_field == '仓位':
                properties[prop_name] = {
                    "number": deal.volume
                }
            elif target_field == '订单ID':
                # 尝试使用Number类型
                properties[prop_name] = {
                    "number": deal.ticket
                }

        return properties

    def sync_deal(self, deal):
        """同步单个成交记录到 Notion"""
        try:
            properties = self.format_deal_to_notion(deal)

            if not properties:
                logger.error(f"[ERROR] 无法格式化订单 {deal.ticket} 的数据")
                return False

            # 创建Notion页面
            response = self.client.pages.create(
                parent={"database_id": self.database_id},
                properties=properties
            )

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
    logger.info("MT5 到 Notion 交易数据同步开始（智能版）")
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

    if not DATABASE_ID:
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

        # 检查数据库结构是否成功
        if not notion_sync.properties_config:
            logger.error("[ERROR] 数据库结构检查失败")
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