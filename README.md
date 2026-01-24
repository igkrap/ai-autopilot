# VS Code Chat Agent MVP (Windows 10/11)

Python + PySide6 기반의 데스크톱 앱으로, VS Code Chat 패널과 유사한 UI에서 화면 캡처 → 모델 계획(JSON) → 액션 실행 루프를 제공합니다.

## 설치

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

## 실행

```bash
python app.py
```

## 사용 방법

### 1) ROI 설정
ROI는 자동화를 허용할 **관심 영역(Region of Interest)** 을 의미합니다.
1. 오른쪽 `Select ROI` 버튼을 클릭합니다.
2. 전체 화면 오버레이에서 드래그하여 ROI 영역을 지정합니다.
3. `Capture Target`을 `roi`로 선택하면 ROI 캡처가 활성화됩니다.

### 2) 모델 설정
`Settings`에서 모델 유형과 엔드포인트 정보를 입력합니다.

- **Stub (기본)**: 오프라인 데모용. `click 100 200`, `type hello` 등 간단 명령을 그대로 액션으로 변환합니다.
- **OpenAI 호환 API**:
  - `Base URL`과 `Model`을 반드시 입력하세요.
  - 예시: `http://localhost:8000` + `gpt-4o-mini` (OpenAI 호환 서버)
- **Ollama**:
  - `Base URL`: `http://localhost:11434`
  - `Model`: `llama3.1` 등

> 모델 응답은 반드시 `{"actions": [...]}` 형태의 JSON이어야 합니다. JSON이 아니면 1회 자동 수정(Repair) 요청 후 중단됩니다.

### 3) 안전 설정
- 위험 키워드(예: 삭제, 전송, 승인)가 감지되면 2단계 확인을 수행합니다.
- ROI 밖 액션은 기본적으로 차단됩니다.
- `Max Actions`는 한 번에 실행되는 액션 수를 제한합니다.

### 4) 세션 저장
- 각 세션은 `sessions/<session_id>/` 아래에 메시지, 캡처, 로그가 저장됩니다.
- 재실행 시 세션 목록이 복원됩니다.

## 알려진 제한 사항
- **Active Window 캡처**는 현재 모니터 전체 캡처로 대체됩니다(Windows API 미사용).
- DPI 스케일링 환경에서는 좌표가 어긋날 수 있습니다. 고정 배율로 테스트하세요.
- 모델에 이미지를 보내는 기능은 구현하지 않았습니다(텍스트 기반 MVP).

## 안전 주의사항
- 업무 시스템/ERP 환경에서는 **테스트 환경**에서만 사용하세요.
- 실제 클릭/입력은 pyautogui를 통해 수행됩니다. 사용 중에는 마우스를 좌측 상단으로 이동하면 FAILSAFE가 동작합니다.
