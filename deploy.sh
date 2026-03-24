#!/bin/bash
# Oracle Cloud Free Tier 배포 스크립트
# 사용법: ssh로 VM 접속 후 이 스크립트 실행
#   curl -fsSL https://raw.githubusercontent.com/BancaKim/KBBank_Knowledge_graph/master/deploy.sh | bash

set -euo pipefail

echo "=== KB Banking Bot 배포 시작 ==="

# 1. Docker 설치 (Ubuntu/Oracle Linux)
if ! command -v docker &> /dev/null; then
    echo ">> Docker 설치 중..."
    sudo apt-get update -y
    sudo apt-get install -y docker.io docker-compose-plugin
    sudo systemctl enable --now docker
    sudo usermod -aG docker "$USER"
    echo ">> Docker 설치 완료. 그룹 반영을 위해 다시 로그인 후 스크립트를 재실행하세요."
    exit 0
fi

# 2. 소스 코드 클론/업데이트
REPO_DIR="$HOME/KBBank_Knowledge_graph"
if [ -d "$REPO_DIR" ]; then
    echo ">> 기존 소스 업데이트..."
    cd "$REPO_DIR" && git pull origin master
else
    echo ">> 소스 클론..."
    git clone https://github.com/BancaKim/KBBank_Knowledge_graph.git "$REPO_DIR"
    cd "$REPO_DIR"
fi

# 3. .env 파일 확인
if [ ! -f .env ]; then
    cp .env.example .env
    echo ""
    echo ">> .env 파일이 생성되었습니다. 반드시 수정하세요:"
    echo "   nano $REPO_DIR/.env"
    echo ""
    echo "   필수 설정:"
    echo "   - NEO4J_PASSWORD=안전한비밀번호"
    echo "   - OPENAI_API_KEY=sk-..."
    echo ""
    echo ">> .env 수정 후 다시 이 스크립트를 실행하세요."
    exit 0
fi

# 4. 방화벽 포트 열기 (80, 7474)
echo ">> 방화벽 포트 확인..."
sudo iptables -I INPUT -p tcp --dport 80 -j ACCEPT 2>/dev/null || true
sudo iptables -I INPUT -p tcp --dport 7474 -j ACCEPT 2>/dev/null || true

# 5. Docker Compose 빌드 & 실행
echo ">> Docker Compose 빌드 & 실행..."
docker compose down 2>/dev/null || true
docker compose up -d --build

echo ""
echo "=== 배포 완료 ==="
echo "앱: http://$(curl -s ifconfig.me)"
echo "Neo4j Browser: http://$(curl -s ifconfig.me):7474"
echo ""
echo "로그 확인: docker compose logs -f"
echo "상태 확인: docker compose ps"
