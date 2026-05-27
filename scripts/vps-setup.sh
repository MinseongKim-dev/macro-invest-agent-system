#!/usr/bin/env bash
# =============================================================================
# Aleph-One VPS Setup Script — Ubuntu 22.04 / 24.04
# Usage: bash vps-setup.sh
# =============================================================================
set -euo pipefail

REPO_URL="https://github.com/MinseongKim-dev/macro-invest-agent-system.git"
DEPLOY_PATH="/opt/aleph-one"
APP_USER="aleph"

# ── 색상 출력 ──────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn()  { echo -e "${YELLOW}[!]${NC} $1"; }
error() { echo -e "${RED}[✗]${NC} $1"; exit 1; }

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  🚀 Aleph-One VPS 자동 설정"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ── 1. 시스템 업데이트 ─────────────────────────────────────────────────────────
info "1/7  시스템 패키지 업데이트..."
apt-get update -qq && apt-get upgrade -y -qq

# ── 2. Docker 설치 ─────────────────────────────────────────────────────────────
info "2/7  Docker 설치..."
if command -v docker &>/dev/null; then
    warn "Docker 이미 설치됨 ($(docker --version)), 스킵"
else
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
    info "Docker 설치 완료"
fi

# ── 3. 방화벽 설정 ─────────────────────────────────────────────────────────────
info "3/7  UFW 방화벽 설정..."
apt-get install -y -qq ufw
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp    comment "SSH"
ufw allow 8001/tcp  comment "Aleph-One API"
ufw --force enable
info "방화벽 설정 완료 (SSH:22, API:8001)"

# ── 4. 배포 디렉터리 구성 ──────────────────────────────────────────────────────
info "4/7  배포 디렉터리 구성..."
mkdir -p "$DEPLOY_PATH"

if [ -d "$DEPLOY_PATH/.git" ]; then
    warn "저장소 이미 존재함, 최신 코드로 업데이트..."
    git -C "$DEPLOY_PATH" fetch origin main
    git -C "$DEPLOY_PATH" reset --hard origin/main
else
    # .env 백업 (있으면)
    ENV_BACKUP=""
    if [ -f "$DEPLOY_PATH/.env" ]; then
        ENV_BACKUP=$(cat "$DEPLOY_PATH/.env")
        warn ".env 백업 완료"
    fi

    # data/ 백업 (내용 있으면)
    DATA_BACKUP="/tmp/aleph-data-backup-$$"
    if [ -d "$DEPLOY_PATH/data" ] && [ -n "$(ls -A "$DEPLOY_PATH/data" 2>/dev/null)" ]; then
        cp -r "$DEPLOY_PATH/data" "$DATA_BACKUP"
        warn "data/ 백업 완료 → $DATA_BACKUP"
    fi

    # 디렉터리 완전 제거 후 새로 클론
    rm -rf "$DEPLOY_PATH"
    git clone --depth=1 "$REPO_URL" "$DEPLOY_PATH"
    info "저장소 클론 완료"

    # 백업 복원
    mkdir -p "$DEPLOY_PATH/data" "$DEPLOY_PATH/logs"
    if [ -n "$ENV_BACKUP" ]; then
        printf '%s' "$ENV_BACKUP" > "$DEPLOY_PATH/.env"
        chmod 600 "$DEPLOY_PATH/.env"
        info ".env 복원 완료"
    fi
    if [ -d "$DATA_BACKUP" ]; then
        cp -r "$DATA_BACKUP/." "$DEPLOY_PATH/data/"
        rm -rf "$DATA_BACKUP"
        info "data/ 복원 완료"
    fi
fi

mkdir -p "$DEPLOY_PATH/data" "$DEPLOY_PATH/logs"

# ── 5. .env 파일 생성 ──────────────────────────────────────────────────────────
info "5/7  .env 파일 설정..."
ENV_FILE="$DEPLOY_PATH/.env"

if [ -f "$ENV_FILE" ]; then
    warn ".env 파일이 이미 존재합니다. 덮어쓰지 않습니다."
    warn "직접 편집하려면: nano $ENV_FILE"
else
    POSTGRES_PASS=$(openssl rand -base64 24 | tr -d '/+=')

    cat > "$ENV_FILE" << EOF
# Aleph-One Production Environment
# ⚠ 이 파일은 절대 Git에 커밋하지 마세요

# ── Docker Image ──────────────────────────────────────────────
# Docker Hub 이미지 경로 (예: yourname/aleph-api)
# GitHub Actions → Settings → Variables → DOCKERHUB_USERNAME 과 동일한 값/aleph-api
DOCKER_IMAGE=alstjd9615/aleph-api
IMAGE_TAG=latest

# ── LLM Provider ───────────────────────────────────────────────
ENV_MODE=PRODUCTION
GROQ_API_KEY=여기에_Groq_API_키_입력
GROQ_MODEL=llama3-70b-8192

# ── Macro Data (FRED) ─────────────────────────────────────────
# 선택: 미설정 시 yfinance 프록시로 자동 폴백 (T10Y, T3M, VIX)
# 무료 발급: https://fred.stlouisfed.org/docs/api/api_key.html
FRED_API_KEY=

# ── Database ──────────────────────────────────────────────────
POSTGRES_PASSWORD=${POSTGRES_PASS}

# ── Milvus Lite ───────────────────────────────────────────────
MILVUS_LITE_PATH=/data/milvus_lite.db

# ── CORS ──────────────────────────────────────────────────────
CORS_ALLOWED_ORIGINS=https://macro-invest-agent-system.vercel.app
EOF

    chmod 600 "$ENV_FILE"
    warn ".env 파일 생성 완료. GROQ_API_KEY를 반드시 수정하세요! (FRED_API_KEY는 선택)"
    warn "편집: nano $ENV_FILE"
fi

# ── 6. GitHub Actions 배포용 SSH 키 생성 ───────────────────────────────────────
info "6/7  GitHub Actions 배포용 SSH 키 생성..."
SSH_KEY_PATH="/root/.ssh/github_actions_deploy"

if [ -f "$SSH_KEY_PATH" ]; then
    warn "배포 SSH 키 이미 존재함, 스킵"
else
    ssh-keygen -t ed25519 -C "github-actions-aleph-deploy" -f "$SSH_KEY_PATH" -N ""
    cat "$SSH_KEY_PATH.pub" >> /root/.ssh/authorized_keys
    chmod 600 /root/.ssh/authorized_keys
    info "SSH 키 생성 완료"
fi

# ── 7. 첫 번째 배포 테스트 ────────────────────────────────────────────────────
info "7/7  Docker Compose 실행 테스트..."
cd "$DEPLOY_PATH"

# .env 파일에서 변수 export
set -a; source "$ENV_FILE"; set +a

if docker compose -f docker-compose.prod.yml config &>/dev/null; then
    info "docker-compose.prod.yml 유효성 검사 통과"
    docker compose -f docker-compose.prod.yml pull 2>/dev/null || warn "이미지 pull 실패 (Docker Hub 크리덴셜 필요할 수 있음)"
    docker compose -f docker-compose.prod.yml up -d timescaledb
    info "TimescaleDB 컨테이너 시작 완료"
else
    warn "Docker Compose 설정 오류 — .env 파일을 확인하세요"
fi

# ── 완료 요약 ──────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✅ VPS 설정 완료"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📋 GitHub Secrets에 등록해야 할 값:"
echo ""
echo "  VPS_SSH_KEY (아래 내용 전체를 복사):"
echo "  ─────────────────────────────────────"
cat "$SSH_KEY_PATH"
echo "  ─────────────────────────────────────"
echo ""
echo "  VPS_HOST     = $(curl -s ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')"
echo "  VPS_USER     = root"
echo "  VPS_PORT     = 22 (기본값, 생략 가능)"
echo "  VPS_DEPLOY_PATH = $DEPLOY_PATH (기본값, 생략 가능)"
echo ""
echo "⚠ 필수 후속 작업:"
echo "  1. nano $ENV_FILE  →  GROQ_API_KEY 입력"
echo "  2. GitHub Secrets에 위 값 등록"
echo "  3. GitHub Variables에 DEPLOY_ENABLED=true 설정"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
