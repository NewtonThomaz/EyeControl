
> **Resumo do Projeto:**  
> O **EyeControl** é uma aplicação desktop leve em Python para Windows que rastreia a atenção visual/inclinação da cabeça do usuário via webcam e reposiciona automaticamente janelas sobrepostas (como *scrcpy*, Picture-in-Picture do navegador ou reprodutores de mídia) entre múltiplos monitores, aplicando deslocamento periférico (*offset*) para não obstruir a linha direta de visão.

---

## 1. Visão Geral e Contexto de Uso

### 1.1 Cenário do Usuário
* **Disposição Física:** Dois monitores empilhados verticalmente.
  * **Monitor Inferior (Principal):** 21 polegadas, resolução $1920 \times 1080$ (105 PPI).
  * **Monitor Superior (Secundário):** 32 polegadas, resolução $1920 \times 1080$ (69 PPI).
* **Disposição Virtual (Windows Display Settings):** Monitor secundário (2) alinhado à direita do monitor principal (1) para navegação confortável com o mouse, com retângulos virtuais consultados dinamicamente via `EnumDisplayMonitors`.
* **Câmera:** Webcam 720p em posição variável (reposicionada com frequência na mesa/monitores).
* **Casos de Uso Primários:** Acompanhar espelhamento do celular (*scrcpy*), vídeos em PiP (YouTube, transmissões) ou janelas flutuantes fixadas no topo via PowerToys (*Always on Top*).

---

## 2. Requisitos Não Funcionais (Eficiência e Sistema)

| ID | Requisito | Detalhamento Técnico |
| :--- | :--- | :--- |
| **RNF-01** | **Consumo Mínimo de Hardware** | Uso de CPU $\le 1.5\%$ e consumo de RAM $\le 80\text{ MB}$ em execução ativa. |
| **RNF-02** | **Amostragem Ajustável (FPS)** | Taxa de leitura configurável pelo usuário na interface, com **padrão inicial travado em 5 FPS**. |
| **RNF-03** | **Redução de Carga de Inferência** | Uso do MediaPipe Face Mesh com `refine_landmarks=False` e redimensionamento interno do frame para $320 \times 240$ antes do processamento. |
| **RNF-04** | **Permissões de Usuário Padrão** | Execução estritamente em **modo de usuário não-elevado (Sem Administrador)**. Respeito ao UIPI (*User Interface Privilege Isolation*) do Windows. |
| **RNF-05** | **Liberação de Periférico (Webcam)** | Ao desativar o rastreamento, o script deve invocar `cap.release()` para liberar o DirectShow/webcam para outros programas (Discord, OBS, Meet). |
| **RNF-06** | **Compatibilidade com PowerToys** | Mover janelas utilizando exclusivamente as flags `SWP_NOZORDER` e `SWP_NOACTIVATE` da Win32 API, preservando o estado de sobreposição sem roubar o foco de digitação. |

---
## 3. Requisitos Funcionais

### 3.1 Seleção de Janela Alvo
* **RF-01 (Dropdown de Processos):** Listar janelas visíveis no Windows que contenham título ativo (filtrando processos em segundo plano do sistema).
* **RF-02 (Recarregar Lista):** Botão para atualizar dinamicamente a listagem de janelas abertas caso o usuário inicie o *scrcpy* ou ative o PiP depois do EyeControl.
* **RF-03 (Manutenção de Dimensões):** O reposicionamento deve alterar apenas as coordenadas $(X, Y)$ da janela, preservando a largura e altura definidas pelo usuário (`SWP_NOSIZE`).

### 3.2 Sistema de Calibração em 2 Pontos (Cruz + Barra de Espaço)
* **RF-04 (Overlay de Calibração):** Janela semitransparente em tela cheia projetando uma cruz gráfica centralizada.
* **RF-05 (Etapa 1 - Monitor Inferior):** Exibe a cruz no centro do monitor de 21" ($1920 \times 1080$). O usuário foca na cruz e pressiona `Espaço`. O sistema calcula e armazena a **mediana das últimas 5 leituras válidas** para o ponto central inferior $(X_{\text{inf}}, Y_{\text{inf}})$.
* **RF-06 (Etapa 2 - Monitor Superior):** A cruz salta para o centro do monitor de 32" ($1920 \times 1080$). O usuário foca e pressiona `Espaço`. O sistema armazena a **mediana das últimas 5 leituras válidas** para o ponto central superior $(X_{\text{sup}}, Y_{\text{sup}})$.
* **RF-07 (Compensação de Perspectiva e Escala Horizontal):** Normaliza a diferença de amplitude e o ângulo assimétrico da webcam móvel utilizando interpolação linear vertical ($\Delta Y = |Y_{\text{sup}} - Y_{\text{inf}}|$) e derivando a amplitude horizontal proporcionalmente à razão de aspecto ($\text{Span}_X = \max(\Delta Y, \epsilon) \times \frac{16}{9}$), evitando divisão por zero no eixo $X$.

### 3.3 Rastreamento Contínuo e Zona Morta (*Deadzone*)
* **RF-08 (Seguimento Contínuo):** A janela acompanha dinamicamente a área de fixação do olhar entre os dois monitores.
* **RF-09 (Zona Morta Configurável):** Slider na interface (intervalo de 10px a 150px) definindo o limiar mínimo de deslocamento necessário para mover a janela, eliminando tremores causados por microssacadas oculares ou ruído do sensor da câmera.

### 3.4 Deslocamento Periférico (*Offset*)
* **RF-10 (Direção do Offset):** Seletor de direção na interface com as opções:
  * `Desligado`
  * `Esquerda`
  * `Direita`
  * `Cima`
  * `Baixo`
* **RF-11 (Distância em Pixels):** Campo numérico / controle deslizante definindo a distância periférica (ex.: de 50px a 600px) a ser somada ao ponto estimado do olhar.
* **RF-12 (Bounding Box / Clamping):** A janela nunca deve ultrapassar as bordas visíveis do monitor no qual está sendo exibida.

### 3.5 Controle de Execução e Atalhos Globais
* **RF-13 (Hotkey Configurável):** Campo de captura de atalho na interface para alternar o rastreamento (*Toggle ON/OFF*). Padrão sugerido: `Ctrl + F9`.
* **RF-14 (Congelamento de Posição):** Ao desligar o rastreamento pelo atalho, a janela permanece exatamente na última posição $(X, Y)$ calculada, sem saltar de volta ao monitor principal.

---

## 4. Mapeamento de Coordenadas (Mundo Físico vs. Virtual)

Como os monitores estão organizados verticalmente na mesa, mas dispostos lado a lado nas configurações do Windows, a lógica de translação aplica o seguinte fluxo matemático:

```

[Webcam / MediaPipe] │ ▼ (Rastreamento do Pitch / Eixo Y do Rosto) Valor de Y relativo │ ├── Se Y >= Limiar Médio (Olhar para Baixo - Monitor 21"): │ X_virtual = X_inferior_base + Offset_X │ Y_virtual = Y_inferior_calculado + Offset_Y │ Área: [0 <= X <= 1920, 0 <= Y <= 1080] │ └── Se Y < Limiar Médio (Olhar para Cima - Monitor 32"): X_virtual = 1920 + X_superior_base + Offset_X Y_virtual = Y_superior_calculado + Offset_Y Área: [X >= 1920, Y ajustado ao offset do Windows]

  

````

---

## 5. Arquitetura da Interface Gráfica (UI)

* **Stack Recomendada:** Python com **CustomTkinter** ou **PyQt6/PySide6** (leve, moderno e sem dependência de serviços externos).
* **Componentes da Janela Principal:**
  1. **Seção Alvo:** Dropdown com lista de janelas ativas + Botão `Atualizar`.
  2. **Seção Desempenho:** Slider de FPS (Faixa: 1 a 15, Valor Inicial: 5).
  3. **Seção Calibração:** Botão `Iniciar Calibração de 2 Pontos` + Status do sensor.
  4. **Seção Offset:** 
     * Seletor de Direção (Esquerda / Direita / Cima / Baixo / Desligado).
     * Slider de Distância (Pixels).
     * Slider de Zona Morta (Deadzone).
  5. **Seção de Atalho:** Campo com captura de atalho de alternância (`Toggle`).
  6. **Barra de Rodapé:** Indicador de status (`Rastreamento: DESATIVADO / ATIVO`, `Webcam: Liberada`).

---

## 6. Chamadas da API Win32 (Prevenção de Conflitos)

Para garantir compatibilidade com o PowerToys e evitar problemas de integridade sem elevação administrativa:

```python
# Mover janela sem roubar foco e sem alterar camada de profundidade (Z-Order)
win32gui.SetWindowPos(
    hwnd_alvo,
    0,                          # Ignorado por causa de SWP_NOZORDER
    pos_x, pos_y,               # Novas coordenadas virtuais
    0, 0,                       # Ignorados por causa de SWP_NOSIZE
    win32con.SWP_NOSIZE | 
    win32con.SWP_NOZORDER | 
    win32con.SWP_NOACTIVATE | 
    win32con.SWP_SHOWWINDOW
)
````

## 7. Próximos Passos e Roadmap de Implementação

1. **Fase 1 (Core Engine):** Script de teste em terminal com captura a 5 FPS, leitura facial via MediaPipe e cálculo de desvio vertical.
2. **Fase 2 (Overlay de Calibração):** Janela translúcida para captura das coordenadas das cruzes centrais com a tecla `Espaço`.
3. **Fase 3 (Gerenciador Win32):** Implementação das chamadas de enumeração de janelas e movimentação via `SetWindowPos`.
4. **Fase 4 (Interface do Usuário):** Integração de todos os controles na GUI com _threads_ separadas (UI na thread principal, captura da webcam e atalhos em threads secundárias de baixo custo).
    

```

Esse documento cobre 100% dos requisitos combinados: as resoluções e dimensões dos monitores (21" 1080p e 32" 1080p), o mapeamento do mundo físico (vertical ou horizontal) para o virtual, a calibração com a cruz e espaço com filtro de mediana, o offset contínuo com zona morta, o atalho de alternância com congelamento de posição, a liberação da câmera e a operação sem privilégios de administrador respeitando o PowerToys.
```