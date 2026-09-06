from utils import (
    save_env, load_env, make_request, _print_error_and_exit,
    display_trailsnap_url, normalize_trailsnap_url,
)
import urllib.request
import urllib.parse
from urllib.error import HTTPError, URLError
import json

def setup_parser(subparsers):
    parser = subparsers.add_parser("config", help="配置 CLI")
    sub_subparsers = parser.add_subparsers(dest="subcommand", help="可用操作")
    sub_subparsers.required = True

    set_parser = sub_subparsers.add_parser("set", help="配置 TrailSnap 地址和 Token")
    set_parser.add_argument("--url", help="TrailSnap 地址 (例如: http://localhost:3180)", required=True)
    set_parser.add_argument("--token", help="API Token (Bearer 凭证)", required=True)
    set_parser.set_defaults(func=execute_set)

    get_parser = sub_subparsers.add_parser("get", help="查看当前配置")
    get_parser.set_defaults(func=execute_get)

    login_parser = sub_subparsers.add_parser("login", help="一键登录换 JWT")
    login_parser.add_argument("--email", help="邮箱账号", required=True)
    login_parser.add_argument("--password", help="密码", required=True)
    login_parser.add_argument("--url", help="API 基础地址 (如果未配置过，则必填)", required=False)
    login_parser.set_defaults(func=execute_login)

    whoami_parser = sub_subparsers.add_parser("whoami", help="查看当前身份")
    whoami_parser.set_defaults(func=execute_whoami)

    test_parser = sub_subparsers.add_parser("test", help="测连接")
    test_parser.set_defaults(func=execute_test)

def execute_set(args):
    try:
        save_env(args.url, args.token)
    except ValueError as error:
        _print_error_and_exit("ConfigError", 400, str(error))

def execute_get(args):
    env = load_env()
    url = env.get("TRAILSNAP_API_URL")
    token = env.get("TRAILSNAP_API_TOKEN")
    if not url:
        print("未配置 API URL，请运行 'config set' 或 'config login'")
    else:
        print(f"TrailSnap 地址: {display_trailsnap_url(url)}")
        if token:
            print(f"API Token: {token[:10]}...{token[-5:]}" if len(token) > 15 else f"API Token: {token}")
        else:
            print("API Token 未配置")

def execute_login(args):
    env = load_env()
    base_url = args.url or env.get("TRAILSNAP_API_URL")
    if not base_url:
        _print_error_and_exit("ConfigError", 401, "API URL 未配置，请通过 --url 参数提供")
    
    try:
        api_base_url = normalize_trailsnap_url(base_url)
    except ValueError as error:
        _print_error_and_exit("ConfigError", 400, str(error))
    login_url = f"{api_base_url}/auth/login"
    
    data = urllib.parse.urlencode({
        "username": args.email,
        "password": args.password
    }).encode("utf-8")
    
    req = urllib.request.Request(login_url, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    
    try:
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode("utf-8"))
            token = result.get("access_token")
            if token:
                save_env(base_url, token)
                print("登录成功！")
            else:
                _print_error_and_exit("APIError", 500, "登录响应中未找到 access_token")
    except HTTPError as e:
        try:
            body = e.read().decode("utf-8")
            body_json = json.loads(body)
            msg = body_json.get("detail", body_json.get("msg", body))
        except Exception:
            msg = str(e)
        _print_error_and_exit("AuthError", e.code, msg)
    except URLError as e:
        _print_error_and_exit("NetworkError", 0, str(e.reason))
    except Exception as e:
        _print_error_and_exit("SystemError", 0, str(e))

def execute_whoami(args):
    user = make_request("/users/me")
    print(f"当前用户: {user.get('email')} (ID: {user.get('id')})")
    if user.get("nickname"):
        print(f"昵称: {user.get('nickname')}")
    if user.get("is_superuser"):
        print("角色: 管理员")
    else:
        print("角色: 普通用户")

def execute_test(args):
    env = load_env()
    base_url = env.get("TRAILSNAP_API_URL")
    token = env.get("TRAILSNAP_API_TOKEN")
    if not base_url:
        _print_error_and_exit("ConfigError", 401, "API URL 未配置，请运行 'config set' 或 'config login'")
    
    print(f"正在测试连接到: {display_trailsnap_url(base_url)}")
    if not token:
        _print_error_and_exit("ConfigError", 401, "API Token 未配置，请运行 'config set' 或 'config login'")
        
    user = make_request("/users/me")
    print(f"连接成功！当前 Token 属于用户: {user.get('email')}")
