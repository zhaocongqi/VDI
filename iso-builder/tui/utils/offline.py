"""离线资源管理工具"""
import os
import subprocess
import logging

logger = logging.getLogger("vdi-installer")


class OfflineManager:
    """离线资源管理器"""

    # ISO 挂载点候选路径
    MOUNT_CANDIDATES = ["/cdrom", "/mnt/iso", "/media/cdrom"]

    def __init__(self):
        self.base_dir = None
        self._detect()

    def _detect(self):
        """检测离线资源路径（兼容 bundle/ 和 offline/）"""
        resource_names = ["bundle", "offline"]
        for path in self.MOUNT_CANDIDATES:
            for name in resource_names:
                resource_path = os.path.join(path, name)
                if os.path.isdir(resource_path):
                    self.base_dir = resource_path
                    logger.info(f"检测到离线资源: {self.base_dir}")
                    return

    def is_available(self):
        """离线资源是否可用"""
        return self.base_dir is not None

    def get_path(self, *parts):
        """获取离线资源路径"""
        if not self.base_dir:
            return None
        return os.path.join(self.base_dir, *parts)

    @property
    def binaries_dir(self):
        return self.get_path("binaries")

    @property
    def images_dir(self):
        return self.get_path("images")

    @property
    def charts_dir(self):
        return self.get_path("charts")

    @property
    def manifests_dir(self):
        return self.get_path("k8s-manifests")

    @property
    def packages_dir(self):
        return self.get_path("packages", "deb")

    def verify_integrity(self):
        """校验离线资源完整性"""
        if not self.is_available():
            return False

        checksum_file = os.path.join(self.base_dir, "checksums.sha256")
        if not os.path.exists(checksum_file):
            logger.warning("checksums.sha256 not found, skipping verification")
            return True

        try:
            result = subprocess.run(
                ["sha256sum", "-c", checksum_file, "--quiet"],
                cwd=self.base_dir,
                capture_output=True, text=True
            )
            if result.returncode == 0:
                logger.info("离线资源校验通过")
                return True
            else:
                logger.error(f"Verification failed: {result.stderr}")
                return False
        except Exception as e:
            logger.error(f"Verification exception: {e}")
            return False

    def load_images(self, component="all"):
        """导入离线容器镜像到 containerd"""
        load_script = self.get_path("..", "scripts", "load-offline-images")
        if load_script and os.path.exists(load_script):
            try:
                subprocess.run(
                    ["bash", load_script, component],
                    check=True, capture_output=True, text=True
                )
                logger.info(f"镜像导入完成: {component}")
                return True
            except subprocess.CalledProcessError as e:
                logger.error(f"Image import failed: {e.stderr}")
                return False
        return False

    def setup_local_repo(self):
        """配置本地 APT 仓库"""
        repo_script = self.get_path("..", "scripts", "setup-local-repo")
        if repo_script and os.path.exists(repo_script):
            try:
                subprocess.run(
                    ["bash", repo_script],
                    check=True, capture_output=True, text=True
                )
                logger.info("本地 APT 仓库配置完成")
                return True
            except subprocess.CalledProcessError as e:
                logger.error(f"APT repo setup failed: {e.stderr}")
                return False
        return False

    def get_manifest(self):
        """读取离线资源清单"""
        # 优先从 bundle/metadata.yaml 读取
        metadata_path = self.get_path("metadata.yaml")
        if metadata_path and os.path.exists(metadata_path):
            try:
                import yaml
                with open(metadata_path, "r") as f:
                    return yaml.safe_load(f)
            except Exception as e:
                logger.error(f"Failed to read metadata: {e}")

        # 回退到 manifest.yaml
        manifest_path = self.get_path("manifest.yaml")
        if not manifest_path or not os.path.exists(manifest_path):
            return None
        try:
            import yaml
            with open(manifest_path, "r") as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to read manifest: {e}")
            return None
