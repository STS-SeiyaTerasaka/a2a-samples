# A2A エージェントシステム構成と実行フロー

このドキュメントでは、`my_a2a_project` で構築されたマルチエージェントシステムの構造と、処理の実行フローを図解します。

## 1. エージェント構成図 (Architecture)

この図は、ローカル環境の Root Agent がどのようにサブエージェントを保持し、それらがクラウド上のエージェントとどのように接続されているかを示しています。

```mermaid
graph TD
    subgraph "Local Environment (Client App)"
        User((User))
        
        subgraph "Root Agent Context"
            Root["Root Agent\n(LlmAgent)"]
            
            subgraph "Research Team (SequentialAgent)"
                ResSeq["Research Agent"]
                Print1["Print Agent\n(Helper)"]
                Res1_Proxy["Research Agent 1\n(RemoteA2aAgent)"]
                Res2_Proxy["Research Agent 2\n(RemoteA2aAgent)"]
            end
            
            subgraph "Write & Review Team (SequentialAgent)"
                WriteSeq["Write & Review Agent"]
                Print2["Print Agent\n(Helper)"]
                Writer_Proxy["Writer Agent\n(RemoteA2aAgent)"]
                Reviewer_Proxy["Review Agent\n(RemoteA2aAgent)"]
            end
        end
    end

    subgraph "Google Cloud (Vertex AI Agent Engine)"
        Cloud_Res1["Research Agent 1\n(Real Instance)"]
        Cloud_Res2["Research Agent 2\n(Real Instance)"]
        Cloud_Writer["Writer Agent\n(Real Instance)"]
        Cloud_Reviewer["Review Agent\n(Real Instance)"]
    end

    %% Relationships
    User <--> Root
    Root -->|Delegate| ResSeq
    Root -->|Delegate| WriteSeq
    
    ResSeq --> Print1
    ResSeq --> Res1_Proxy
    ResSeq --> Res2_Proxy
    
    WriteSeq --> Print2
    WriteSeq --> Writer_Proxy
    WriteSeq --> Reviewer_Proxy
    
    %% A2A Connections
    Res1_Proxy -.->|A2A Protocol / HTTP| Cloud_Res1
    Res2_Proxy -.->|A2A Protocol / HTTP| Cloud_Res2
    Writer_Proxy -.->|A2A Protocol / HTTP| Cloud_Writer
    Reviewer_Proxy -.->|A2A Protocol / HTTP| Cloud_Reviewer

    classDef local fill:#e1f5fe,stroke:#01579b,stroke-width:2px;
    classDef cloud fill:#fff3e0,stroke:#ff6f00,stroke-width:2px;
    classDef root fill:#d1c4e9,stroke:#512da8,stroke-width:2px;
    
    class ResSeq,WriteSeq,Print1,Print2,Res1_Proxy,Res2_Proxy,Writer_Proxy,Reviewer_Proxy local;
    class Cloud_Res1,Cloud_Res2,Cloud_Writer,Cloud_Reviewer cloud;
    class Root root;
```

---

## 2. 実行フロー図 (Sequence)

ユーザーが記事作成を依頼してから、最終的な記事が出力されるまでの処理の流れです。

```mermaid
sequenceDiagram
    actor User
    participant Root as Root Agent
    participant ResTeam as "Research Team\n(Sequential)"
    participant Res1 as "Remote Res1\n(Topic)"
    participant Res2 as "Remote Res2\n(Report)"
    participant WriteTeam as "Write Team\n(Sequential)"
    participant Writer as "Remote Writer"
    participant Reviewer as "Remote Reviewer"

    User->>Root: 「〇〇について記事を書いて」
    
    Note over Root: 指示(Instruction)に従い<br/>まずは調査が必要と判断

    Root->>ResTeam: 処理を委譲 (Delegate)
    activate ResTeam
    
    ResTeam->>User: (Print) "調査を開始します..."
    
    ResTeam->>Res1: 調査項目を選定依頼 (A2A)
    activate Res1
    Res1-->>ResTeam: 項目リスト返却
    deactivate Res1
    
    ResTeam->>User: (Print) "選定トピックに基づきレポート作成..."
    
    ResTeam->>Res2: 調査レポート作成依頼 (A2A)
    activate Res2
    Res2-->>ResTeam: 調査レポート返却
    deactivate Res2
    
    ResTeam->>User: (Print) "調査完了。作成に進みますか？"
    ResTeam-->>Root: 完了通知
    deactivate ResTeam

    Root->>User: "調査が終わりました。記事作成しますか？"
    User->>Root: "お願いします"

    Note over Root: 記事作成チームへ委譲

    Root->>WriteTeam: 処理を委譲 (Delegate)
    activate WriteTeam
    
    WriteTeam->>User: (Print) "記事を執筆します..."
    
    WriteTeam->>Writer: 記事執筆依頼 (A2A)
    activate Writer
    Writer-->>WriteTeam: 記事ドラフト
    deactivate Writer
    
    WriteTeam->>User: (Print) "レビューを実施します..."
    
    WriteTeam->>Reviewer: 記事レビュー依頼 (A2A)
    activate Reviewer
    Reviewer-->>WriteTeam: 修正コメント
    deactivate Reviewer
    
    WriteTeam->>User: (Print) "修正依頼しますか？"
    WriteTeam-->>Root: 完了通知
    deactivate WriteTeam

    Root->>User: 最終結果表示
```