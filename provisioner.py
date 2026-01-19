#!/usr/bin/env python3
"""
Tamesuke プロビジョニングスクリプト
File Server方式（WebDAV経由でメタデータ配信）
"""

from typing import Any, Dict, Optional
import time
import json
import os
import re
from datetime import datetime, timezone
from dotenv import load_dotenv


class TamesukeProvisioner:
    """
    サービスのプロビジョニングを行うクラス
    """
    
    def __init__(
        self,
        proxmox_host: str,
        proxmox_user: str,
        proxmox_password: str,
        cloudflare_token: str,
        cloudflare_account_id: str,
        cloudflare_zone_id: str,
        fileserver_host: str,
        fileserver_port: int = 8080,
        domain: str = "persys.jp",
        proxmox_node: str = "odin"
    ):
        """
        初期化
        
        Args:
            proxmox_host: Proxmoxホストのアドレス
            proxmox_user: Proxmoxユーザー（例: root@pam）
            proxmox_password: Proxmoxパスワード
            cloudflare_token: Cloudflare APIトークン
            cloudflare_account_id: CloudflareアカウントID
            cloudflare_zone_id: Cloudflare Zone ID
            fileserver_host: File ServerのIPアドレス
            fileserver_port: File Serverのポート番号
            domain: 使用するドメイン（デフォルト: persys.jp）
            proxmox_node: Proxmoxノード名（デフォルト: odin）
        """
        self.proxmox_host = proxmox_host
        self.proxmox_user = proxmox_user
        self.proxmox_password = proxmox_password
        self.cloudflare_token = cloudflare_token
        self.cloudflare_account_id = cloudflare_account_id
        self.cloudflare_zone_id = cloudflare_zone_id
        self.fileserver_host = fileserver_host
        self.fileserver_port = fileserver_port
        self.domain = domain
        self.node = proxmox_node
        
        # API接続オブジェクト（後で初期化）
        self.proxmox = None
        self.cf = None
        
        # OSSタイプとテンプレートIDのマッピング
        # 8010: cloudflare-tunnel-base（ベーステンプレート）
        # 8011: nginx-template（8010 + nginx）
        # 8012: growi-template（8010 + growi）- 将来追加
        self.template_map = {
            'nginx': 8011,
            # 'growi': 8012,  # 将来追加
            # 'snipeit': 8013,
        }
        
        # OSSタイプとポート番号のマッピング
        self.port_map = {
            'nginx': 80,
            'growi': 3000,
            'snipeit': 80,
        }
    
    def connect(self):
        """
        ProxmoxとCloudflareに接続
        """
        try:
            # Proxmox接続
            from proxmoxer import ProxmoxAPI
            self.proxmox = ProxmoxAPI(
                self.proxmox_host,
                user=self.proxmox_user,
                password=self.proxmox_password,
                verify_ssl=False
            )
            version = self.proxmox.version.get()
            print(f"[OK] Proxmox connected: {version['version']}")
            
            # Cloudflare接続
            from cloudflare import Cloudflare
            self.cf = Cloudflare(api_token=self.cloudflare_token)
            print("[OK] Cloudflare connected")
            
        except ImportError as e:
            print(f"[ERROR] ライブラリが見つかりません: {e}")
            print("\n以下のコマンドでインストールしてください:")
            print("  pip install -r requirements.txt")
            raise
        except Exception as e:
            print(f"[ERROR] 接続エラー: {e}")
            raise
    
    def _validate_subdomain(self, subdomain: str):
        """
        サブドメインのバリデーション
        
        Args:
            subdomain: サブドメイン
        
        Raises:
            ValueError: バリデーションエラー
        """
        # 長さチェック（12文字以内）
        if len(subdomain) > 12:
            raise ValueError(
                f"サブドメインは12文字以内にしてください（現在: {len(subdomain)}文字）"
            )
        
        # 文字種チェック（英小文字、数字、ハイフンのみ）
        if not re.match(r'^[a-z0-9-]+$', subdomain):
            raise ValueError(
                f"サブドメインは英小文字、数字、ハイフンのみ使用可能: {subdomain}"
            )
        
        # ハイフン始まり・終わりチェック
        if subdomain.startswith('-') or subdomain.endswith('-'):
            raise ValueError(
                f"サブドメインはハイフンで始まる・終わることはできません: {subdomain}"
            )

    def _rollback(
        self,
        resources: Dict[str, Any],
        subdomain: str
    ):
        """
        プロビジョニング失敗時のロールバック処理
        作成済みのリソースを逆順でクリーンアップ

        Args:
            resources: 作成済みリソースの辞書
            subdomain: サブドメイン
        """
        print("\n[ROLLBACK] ロールバック処理を開始します...")

        # LXCコンテナの削除（起動済みの場合は停止してから削除）
        if 'vmid' in resources:
            vmid = resources['vmid']
            try:
                print(f"   - LXC {vmid} を停止中...")
                try:
                    self.proxmox.nodes(self.node).lxc(vmid).status.stop.post()
                    time.sleep(3)
                except Exception:
                    pass  # 既に停止している場合は無視

                print(f"   - LXC {vmid} を削除中...")
                self.proxmox.nodes(self.node).lxc(vmid).delete()
                print(f"   - [OK] LXC {vmid} を削除しました")
            except Exception as e:
                print(f"   - [WARN] LXC {vmid} の削除に失敗: {e}")

        # メタデータファイルの削除
        if 'metadata_uploaded' in resources:
            vmid = resources.get('vmid')
            if vmid:
                try:
                    import requests
                    url = f'http://{self.fileserver_host}:{self.fileserver_port}/upload/metadata-{vmid}.json'
                    print(f"   - メタデータファイル削除中...")
                    requests.delete(url, timeout=10)
                    print(f"   - [OK] メタデータファイルを削除しました")
                except Exception as e:
                    print(f"   - [WARN] メタデータファイルの削除に失敗: {e}")

        # DNSレコードの削除
        if 'dns_record_id' in resources:
            try:
                print(f"   - DNSレコード削除中...")
                self.cf.dns.records.delete(
                    resources['dns_record_id'],
                    zone_id=self.cloudflare_zone_id
                )
                print(f"   - [OK] DNSレコードを削除しました")
            except Exception as e:
                print(f"   - [WARN] DNSレコードの削除に失敗: {e}")

        # Cloudflare Tunnelの削除
        if 'tunnel_id' in resources:
            try:
                print(f"   - Tunnel削除中...")
                self.cf.zero_trust.tunnels.cloudflared.delete(
                    resources['tunnel_id'],
                    account_id=self.cloudflare_account_id
                )
                print(f"   - [OK] Tunnelを削除しました")
            except Exception as e:
                print(f"   - [WARN] Tunnelの削除に失敗: {e}")

        print("[ROLLBACK] ロールバック処理が完了しました\n")

    def provision(
        self,
        customer_email: str,
        oss_type: str,
        subdomain: str,
        duration_days: int
    ) -> Dict[str, Any]:
        """
        メインプロビジョニング処理
        
        Args:
            customer_email: 顧客メールアドレス
            oss_type: OSSタイプ（nginx/growi/snipeit等）
            subdomain: サブドメイン（12文字以内、英小文字・数字・ハイフンのみ）
            duration_days: 利用期間（日数）
        
        Returns:
            プロビジョニング結果の辞書
        """
        print(f"\n{'='*60}")
        print(f"プロビジョニング開始")
        print(f"{'='*60}")
        print(f"顧客: {customer_email}")
        print(f"OSS: {oss_type}")
        print(f"サブドメイン: {subdomain}")
        print(f"ドメイン: {self.domain}")
        print(f"期間: {duration_days}日")
        print(f"{'='*60}\n")
        
        # 入力検証
        self._validate_subdomain(subdomain)
        
        if oss_type not in self.template_map:
            raise ValueError(f"未対応のOSSタイプ: {oss_type}")
        
        # 接続確認
        if self.proxmox is None or self.cf is None:
            self.connect()

        # ロールバック用にリソースをトラッキング
        created_resources: Dict[str, Any] = {}

        try:
            # Step 1: VMID割り当て
            vmid = self._get_next_vmid()
            print(f"1. [OK] VMID割り当て: {vmid}")

            # Step 2: Cloudflare Tunnel作成
            tunnel = self._create_tunnel(vmid, subdomain)
            tunnel_id = tunnel.id
            created_resources['tunnel_id'] = tunnel_id
            print(f"2. [OK] Tunnel作成: {tunnel_id}")

            # Step 3: Tunnel Token取得
            tunnel_token = self._get_tunnel_token(tunnel)
            print(f"3. [OK] Tunnel Token取得")

            # Step 4: Tunnel設定
            self._configure_tunnel(tunnel_id, subdomain, oss_type)
            print(f"4. [OK] Tunnelルーティング設定")

            # Step 5: DNS登録
            dns_record_id = self._create_dns_record(subdomain, tunnel_id)
            created_resources['dns_record_id'] = dns_record_id
            print(f"5. [OK] DNS登録: {subdomain}.{self.domain}")

            # Step 6: メタデータJSON作成
            metadata = self._create_metadata(
                vmid, customer_email, subdomain, oss_type, tunnel_token
            )
            print(f"6. [OK] メタデータJSON作成")

            # Step 7: File Serverへアップロード
            self._upload_metadata(vmid, metadata)
            created_resources['vmid'] = vmid
            created_resources['metadata_uploaded'] = True
            print(f"7. [OK] File Serverへアップロード")

            # Step 8: LXCクローン
            self._clone_lxc(vmid, oss_type, subdomain)
            print(f"8. [OK] LXCクローン作成")

            # Step 9: LXC起動
            self._start_lxc(vmid)
            print(f"9. [OK] LXC起動")

            # Step 10: 初期化完了待機
            url = f"https://{subdomain}.{self.domain}"
            print(f"10. [WAIT] 初期化完了待機中... (最大5分)")
            self._wait_for_ready(url, timeout=300)
            print(f"10. [OK] サービス起動完了")

            result = {
                'vmid': vmid,
                'tunnel_id': tunnel_id,
                'url': url,
                'status': 'active'
            }

            print(f"\n{'='*60}")
            print(f"プロビジョニング完了!")
            print(f"{'='*60}")
            print(f"URL: {url}")
            print(f"VMID: {vmid}")
            print(f"Tunnel ID: {tunnel_id}")
            print(f"{'='*60}\n")

            return result

        except Exception as e:
            print(f"\n[ERROR] エラーが発生しました: {e}")
            self._rollback(created_resources, subdomain)
            raise
    
    def _get_next_vmid(self) -> int:
        """
        利用可能なVMIDを取得（9000～9999の範囲）
        
        Returns:
            利用可能なVMID
        """
        resources = self.proxmox.cluster.resources.get(type='vm')
        used_vmids = {resource['vmid'] for resource in resources}
        
        for vmid in range(9000, 10000):
            if vmid not in used_vmids:
                return vmid
        
        raise Exception("利用可能なVMIDがありません（9000-9999がすべて使用中）")
    
    def _create_tunnel(self, vmid: int, subdomain: str):
        """
        Cloudflare Tunnelを作成
        既存の同名Tunnelがあれば削除してから作成
        
        Args:
            vmid: VMID
            subdomain: サブドメイン
        
        Returns:
            Tunnelオブジェクト
        """
        import secrets
        
        tunnel_name = f"service-{vmid}-{subdomain}"
        
        # 既存Tunnelをチェック
        existing_tunnels = self.cf.zero_trust.tunnels.cloudflared.list(
            account_id=self.cloudflare_account_id,
            name=tunnel_name
        )
        
        # 同名のTunnelがあれば削除
        for tunnel in existing_tunnels:
            if tunnel.name == tunnel_name:
                print(f"   - 既存Tunnel削除: {tunnel.id}")
                self.cf.zero_trust.tunnels.cloudflared.delete(
                    tunnel.id,
                    account_id=self.cloudflare_account_id
                )
        
        # 新しいTunnel作成
        tunnel_secret = secrets.token_bytes(32).hex()
        tunnel = self.cf.zero_trust.tunnels.cloudflared.create(
            account_id=self.cloudflare_account_id,
            name=tunnel_name,
            tunnel_secret=tunnel_secret
        )
        
        return tunnel
    
    def _get_tunnel_token(self, tunnel) -> str:
        """
        Tunnel Tokenを取得
        
        Args:
            tunnel: create_tunnelの戻り値
        
        Returns:
            Tunnel Token文字列
        """
        token = self.cf.zero_trust.tunnels.cloudflared.token.get(
            tunnel.id,
            account_id=self.cloudflare_account_id
        )
        
        return token
    
    def _configure_tunnel(self, tunnel_id: str, subdomain: str, oss_type: str):
        """
        Tunnelのルーティング設定
        
        Args:
            tunnel_id: Tunnel ID
            subdomain: サブドメイン
            oss_type: OSSタイプ
        """
        port = self.port_map[oss_type]
        hostname = f"{subdomain}.{self.domain}"
        
        config = {
            'ingress': [
                {
                    'hostname': hostname,
                    'service': f'http://localhost:{port}'
                },
                {
                    'service': 'http_status:404'
                }
            ]
        }
        
        self.cf.zero_trust.tunnels.cloudflared.configurations.update(
            tunnel_id,
            account_id=self.cloudflare_account_id,
            config=config
        )
    
    def _create_dns_record(self, subdomain: str, tunnel_id: str) -> str:
        """
        Cloudflare DNSレコードを作成
        既存の同名レコードがあれば削除してから作成

        Args:
            subdomain: サブドメイン
            tunnel_id: Tunnel ID

        Returns:
            作成したDNSレコードのID
        """
        # 既存DNSレコードをチェック
        existing_records = self.cf.dns.records.list(
            zone_id=self.cloudflare_zone_id,
            name=f"{subdomain}.{self.domain}"
        )

        # 同名のレコードがあれば削除
        for record in existing_records:
            if record.name == f"{subdomain}.{self.domain}":
                print(f"   - 既存DNSレコード削除: {record.id}")
                self.cf.dns.records.delete(
                    record.id,
                    zone_id=self.cloudflare_zone_id
                )

        # 新しいDNSレコード作成
        dns_record = {
            'type': 'CNAME',
            'name': subdomain,
            'content': f'{tunnel_id}.cfargotunnel.com',
            'ttl': 1,  # Automatic
            'proxied': True
        }

        result = self.cf.dns.records.create(
            zone_id=self.cloudflare_zone_id,
            **dns_record
        )

        return result.id
    
    def _create_metadata(
        self,
        vmid: int,
        email: str,
        subdomain: str,
        oss_type: str,
        tunnel_token: str
    ) -> dict:
        """
        メタデータJSONを作成
        
        Args:
            vmid: VMID
            email: 顧客メールアドレス
            subdomain: サブドメイン
            oss_type: OSSタイプ
            tunnel_token: Tunnel Token
        
        Returns:
            メタデータ辞書
        """
        metadata = {
            'vmid': vmid,
            'hostname': subdomain,
            'subdomain': subdomain,
            'customer_email': email,
            'oss_type': oss_type,
            'url': f'https://{subdomain}.{self.domain}',
            'tunnel_token': tunnel_token,
            'created_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        }
        
        return metadata
    
    def _upload_metadata(self, vmid: int, metadata: dict):
        """
        File Serverにメタデータをアップロード
        
        Args:
            vmid: VMID
            metadata: メタデータ辞書
        """
        import requests
        
        url = f'http://{self.fileserver_host}:{self.fileserver_port}/upload/metadata-{vmid}.json'
        metadata_json = json.dumps(metadata, indent=2)
        
        response = requests.put(
            url,
            data=metadata_json,
            headers={'Content-Type': 'application/json'},
            timeout=10
        )
        
        if response.status_code not in [200, 201, 204]:
            raise Exception(f"File Serverへのアップロード失敗: {response.status_code}")
    
    def _clone_lxc(self, vmid: int, oss_type: str, subdomain: str):
        """
        テンプレートからLXCをクローン
        
        Args:
            vmid: 新しいVMID
            oss_type: OSSタイプ
            subdomain: サブドメイン（ホスト名として使用）
        """
        template_id = self.template_map[oss_type]
        
        # ホスト名 = サブドメイン
        hostname = subdomain
        
        self.proxmox.nodes(self.node).lxc(template_id).clone.post(
            newid=vmid,
            hostname=hostname,
            full=1,  # フルクローン
            storage='vm-storage'  # ZFS保護ストレージ
        )
        
        # クローン完了待機
        time.sleep(5)
    
    def _start_lxc(self, vmid: int):
        """
        LXCを起動
        
        Args:
            vmid: VMID
        """
        self.proxmox.nodes(self.node).lxc(vmid).status.start.post()
        
        # 起動待機
        time.sleep(3)
    
    def _wait_for_ready(self, url: str, timeout: int = 300):
        """
        サービスが起動するまで待機
        
        Args:
            url: チェックするURL
            timeout: タイムアウト秒数
        """
        import requests
        
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                response = requests.get(url, timeout=5, verify=False)
                if response.status_code < 500:
                    return True
            except requests.exceptions.RequestException:
                pass
            
            time.sleep(10)
            elapsed = int(time.time() - start_time)
            print(f"   {elapsed}秒経過...", end='\r')
        
        raise Exception(f"タイムアウト: {timeout}秒以内にサービスが起動しませんでした")


# ========================================
# 使用例
# ========================================

if __name__ == '__main__':
    """
    使用例：環境変数から読み込んで実行
    """
    
    # .envファイルを読み込む
    load_dotenv()
    
    # 環境変数から設定を取得
    provisioner = TamesukeProvisioner(
        proxmox_host=os.getenv('PROXMOX_HOST'),
        proxmox_user=os.getenv('PROXMOX_USER'),
        proxmox_password=os.getenv('PROXMOX_PASSWORD'),
        cloudflare_token=os.getenv('CLOUDFLARE_API_TOKEN'),
        cloudflare_account_id=os.getenv('CLOUDFLARE_ACCOUNT_ID'),
        cloudflare_zone_id=os.getenv('CLOUDFLARE_ZONE_ID'),
        fileserver_host=os.getenv('FILESERVER_HOST'),
        fileserver_port=int(os.getenv('FILESERVER_PORT', 8080)),
        domain=os.getenv('DOMAIN', 'persys.jp'),
        proxmox_node=os.getenv('PROXMOX_NODE', 'odin')
    )
    
    # プロビジョニング実行
    result = provisioner.provision(
        customer_email='test@example.com',
        oss_type='nginx',
        subdomain='demo',
        duration_days=7
    )
    
    print(f"\n結果: {json.dumps(result, indent=2)}")
