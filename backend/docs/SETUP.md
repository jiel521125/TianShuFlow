# Setup Guide

Quick setup instructions for TianShu.

## Configuration Setup

TianShu uses a YAML configuration file that should be placed in the **project root directory**.

### Steps

1. **Navigate to project root**:
   ```bash
   cd /path/to/tian-shu
   ```

2. **Copy example configuration**:
   ```bash
   cp config.example.yaml config.yaml
   ```

3. **Edit configuration**:
   ```bash
   # Option A: Set environment variables (recommended)
   export OPENAI_API_KEY="your-key-here"

   # Optional: pin the project root when running from another directory
   export TIAN_SHU_PROJECT_ROOT="/path/to/tian-shu"

   # Option B: Edit config.yaml directly
   vim config.yaml  # or your preferred editor
   ```

4. **Verify configuration**:
   ```bash
   cd backend
   python -c "from tianshu.config import get_app_config; print('✓ Config loaded:', get_app_config().models[0].name)"
   ```

## Important Notes

- **Location**: `config.yaml` should be in `tian-shu/` (project root)
- **Git**: `config.yaml` is automatically ignored by git (contains secrets)
- **Runtime root**: Set `TIAN_SHU_PROJECT_ROOT` if TianShu may start from outside the project root
- **Runtime data**: State defaults to `.tian-shu` under the project root; set `TIAN_SHU_HOME` to move it
- **Skills**: Skills default to `skills/` under the project root; set `TIAN_SHU_SKILLS_PATH` or `skills.path` to move them

## Configuration File Locations

The backend searches for `config.yaml` in this order:

1. Explicit `config_path` argument from code
2. `TIAN_SHU_CONFIG_PATH` environment variable (if set)
3. `config.yaml` under `TIAN_SHU_PROJECT_ROOT`, or the current working directory when `TIAN_SHU_PROJECT_ROOT` is unset
4. Legacy backend/repository-root locations for monorepo compatibility

**Recommended**: Place `config.yaml` in project root (`tian-shu/config.yaml`).

## Sandbox Setup (Optional but Recommended)

If you plan to use Docker/Container-based sandbox (configured in `config.yaml` under `sandbox.use: tianshu.community.aio_sandbox:AioSandboxProvider`), it's highly recommended to pre-pull the container image:

```bash
# From project root
make setup-sandbox
```

**Why pre-pull?**
- The sandbox image (~500MB+) is pulled on first use, causing a long wait
- Pre-pulling provides clear progress indication
- Avoids confusion when first using the agent

If you skip this step, the image will be automatically pulled on first agent execution, which may take several minutes depending on your network speed.

## Troubleshooting

### Config file not found

```bash
# Check where the backend is looking
cd tian-shu/backend
python -c "from tianshu.config.app_config import AppConfig; print(AppConfig.resolve_config_path())"
```

If it can't find the config:
1. Ensure you've copied `config.example.yaml` to `config.yaml`
2. Verify you're in the project root, or set `TIAN_SHU_PROJECT_ROOT`
3. Check the file exists: `ls -la config.yaml`

### Permission denied

```bash
chmod 600 ../config.yaml  # Protect sensitive configuration
```

## See Also

- [Configuration Guide](CONFIGURATION.md) - Detailed configuration options
- [Architecture Overview](../CLAUDE.md) - System architecture
