"""生成服务端签名密钥（写入 .env 的 LICENSE_SECRET）。

注意：此密钥必须与 skill 端 config/license_pub.key 保持一致，
才能让客户端离线校验服务端发的激活码。
"""
import secrets


def main():
    secret = secrets.token_urlsafe(48)
    print(f"LICENSE_SECRET={secret}")
    print()
    print("1) 将以上值写入 .env 的 LICENSE_SECRET")
    print("2) 同时写入 skill 目录 config/license_pub.key（覆盖占位密钥），")
    print("   并重新注册 skill，客户端即可离线校验本服务发出的激活码")


if __name__ == "__main__":
    main()
