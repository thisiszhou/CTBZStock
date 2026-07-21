import json
import uuid
import pytz
import requests
from datetime import datetime
from loguru import logger
import attrdict
from config import cons
'''
1 service 对象初始化，请求 access_token， 存到 redis，设置过期时间
2 每次请求过来，先看 token，如果 token 失效，更新 token
3 如果无法更新 token，返回失败

飞书 API 文档
https://open.feishu.cn/document/ukTMukTMukTM/uADN14CM0UjLwQTN
'''


class CustomerDataError(Exception):
    def __init__(self, message='', code=-1):
        self.code = code
        self.message = message

    def __str__(self):
        if self.message:
            return self.message
        else:
            return 'Customer data error'


class FeishuService:
    def __init__(self, conf):
        self.conf = conf
        self.session = self.create_request_session()
        self.cache = {}
        self.timezone = pytz.timezone('Asia/Shanghai')
        self.headers = {
            "Content-Type": "application/json; charset=utf-8"
        }
        self.robot = '量化交易'

    def create_request_session(self):
        MAX_RETRIES = 3
        session = requests.Session()
        adapter = requests.sessions.HTTPAdapter(max_retries=MAX_RETRIES)
        session.mount('https://', adapter)
        session.mount('http://', adapter)
        return session

    def update_tenant_access_token(self):
        try:
            body = {
                'app_id': self.conf.app_id,
                'app_secret': self.conf.app_secret
            }
            response = self.session.post(self.conf.access_token_url, data=json.dumps(body), timeout=30)
            response.raise_for_status()
            resp_data = json.loads(response.text)
            # logger.debug(f'get access_token:{resp_data}, success')
            access_token = resp_data.get('tenant_access_token', None)
            expire = resp_data.get('expire', 999999)
            if not access_token:
                raise CustomerDataError('update Feishu access token failed')
            # 0.9让我们的过期时间比飞书的提前一点
            self.cache.setdefault('access_token', access_token)
            return access_token
        except Exception as err:
            logger.warning(f'{err.__class__.__name__}:{err}, update access token failed')
            return None

    @property
    def access_token(self):
        access_token = self.cache.get('access_token')
        if not access_token:
            access_token = self.update_tenant_access_token()
            if not access_token:
                raise CustomerDataError('update Feishu access token failed')
        return access_token

    def send_to_user(self, message, user_name):
        '''
        发送消息到用户
        '''
        user_id = self.find_user_id(user_name)
        self.check_argument(message, user_id, user_name)
        body = dict(self.conf.user_message_template)
        body['user_id'] = user_id
        body['content']['text'] = self.make_message(message)
        resp_data = self.do_auth_request(self.session.post, body)
        status = 'success' if resp_data['code'] == 0 else 'failed'
        ret_message = f'send:{body} to user:{user_name}({user_id}) {status}, response:{resp_data}'
        # logger.debug(ret_message)
        return ret_message

    def send_to_group(self, message, group_name, at_users=[], check_message_length=True):
        '''
        发送消息到群
        '''
        group_id = self.find_group_id(group_name)
        if check_message_length:
            self.check_argument(message, group_id, group_name)
        body = dict(self.conf.group_message_template)
        body['chat_id'] = group_id
        body['content']['text'] = self.make_message(message) + self.make_at_users(at_users)
        resp_data = self.do_auth_request(self.session.post, body)
        status = 'success' if resp_data['code'] == 0 else 'failed'
        ret_message = f'send:{body} to group:{group_name}({group_id}) {status}, response:{resp_data}'
        # logger.debug(ret_message)
        return ret_message

    def send_to_users(self, message, user_names):
        '''
        发送消息到多个用户
        '''
        ret = dict()
        for name in user_names:
            ret.update({name: self.send_to_user(message, name)})
        return json.dumps(ret, ensure_ascii=False)

    def send_to_groups(self, message, group_names):
        '''
        发送消息到多个群组
        '''
        ret = dict()
        for group in group_names:
            ret.update({group: self.send_to_group(message, group)})
        return json.dumps(ret, ensure_ascii=False)

    def do_auth_request(self, request_method, body):
        '''
        发送请求到飞书API
        '''
        headers = dict(self.headers)
        headers.update({'Authorization': f'Bearer {self.access_token}'})
        # logger.debug(f'url:{self.conf.message_send_url}, body:{body}, headers:{headers}')
        response = request_method(
            self.conf.message_send_url,
            headers=headers,
            data=json.dumps(body).encode('utf-8'),
            timeout=30)
        response.raise_for_status()
        return json.loads(response.text)

    def get_group_list(self):
        groups = self.cache.get('feishu_groups')
        if groups:
            groups = json.loads(groups)
            return groups

        headers = dict(self.headers)
        headers.update({'Authorization': f'Bearer {self.access_token}'})
        # logger.debug(f'url:{self.conf.message_send_url}, headers:{headers}')
        response = self.session.get(
            self.conf.chat_url,
            headers=headers,
            timeout=30)
        response.raise_for_status()
        groups = json.loads(response.text)['data']['groups']
        self.cache.setdefault('feishu_groups', json.dumps(groups))
        return groups

    def get_user_list(self):
        return self.conf.user_list

    def make_message(self, message):
        '''
        构造消息体，在message里面附加上看门狗的前缀和时间戳后缀
        '''
        prefix = ''
        timestamp = datetime.now(tz=self.timezone).strftime('%Y-%m-%d %H:%M:%S %Z%z')
        return prefix + message + f' [{timestamp}]'

    def make_at_users(self, users):
        '''
        添加 @ 用户的标签
        '''
        if len(users) == 0:
            return ''
        at_list = [f'<at user_id="{self.find_user_id(user_name)}"></at>'
                   for user_name in users if self.find_user_id(user_name)]
        return ' '.join(at_list)

    def check_argument(self, message, item_id, name):
        '''
        参数检查
        '''
        if len(message) > self.conf.max_message_length:
            err_msg = f'size={len(message)}, message is too long'
            raise CustomerDataError(err_msg)
        if not item_id:
            err_msg = f'can not find item id for name:{name}'
            raise CustomerDataError(err_msg)

    def find_group_id(self, group_name):
        '''
        根据群名称，查找飞书 chat_id
        '''
        for item in list(self.conf.group_alias):
            if item['name'] == group_name:
                # logger.info(f'get group_id:{item["chat_id"]} by group_name:{group_name} in group alias')
                return item['chat_id']

        for item in list(self.get_group_list()):
            if item['name'] == group_name:
                # logger.info(f'get group_id:{item["chat_id"]} by group_name:{group_name} in group')
                return item['chat_id']
        return None

    def find_user_id(self, user_name):
        '''
        根据用户名称（可以是姓名，电话，邮箱），查找飞书user_id
        '''
        user_id = None
        for item in self.conf.user_list:
            if user_name in (item['user_name'], item['mobile'], item['email']):
                user_id = item['user_id']
        # logger.info(f'get user_id:{user_id} by user_name:{user_name}')
        return user_id

    def check_send_frequency(self, send_force: bool, name: str):
        '''
        是否强制发送，而不受沉默周期(conf.slience_interval)的限制
        '''
        key = f'send_{name}'
        if send_force:
            self.cache.setdefault(key, 1)
            return True
        ret = self.cache.get(key) is None
        if ret:
            self.cache.setdefault(key, 1,)
        return ret

    def get_watch_dog_tag(self):
        '''
        获得一个狗牌
        '''
        return uuid.uuid4().hex


def _feishu_config(notice_group: str = ""):
    return {
        "app_id": cons.FEISHU_APP_ID,
        "app_secret": cons.FEISHU_APP_SECRET,
        "message_send_url": "https://open.feishu.cn/open-apis/message/v4/send/",
        "chat_url": "https://open.feishu.cn/open-apis/chat/v4/list",
        "access_token_url": "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal/",
        "max_message_length": 2048,
        "notice_group": notice_group or cons.FEISHU_GROUP,
        "group_alias": [],
        "group_message_template": {
            "chat_id": None,
            "msg_type": "text",
            "content": {
                "text": None
            }
        },
    }


def send_group_msg(group="", msg="this is test"):
    conf = attrdict.AttrDict(_feishu_config(group))
    feishu_service = FeishuService(conf)
    ret_message = feishu_service.send_to_group(msg + "\n\n", conf.notice_group, at_users=[],
                                               check_message_length=False)
    # logger.info(ret_message)


if __name__ == "__main__":
    send_group_msg(cons.FEISHU_GROUP, "test message")
