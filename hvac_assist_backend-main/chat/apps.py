from django.apps import AppConfig


class ChatConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'chat'

    def ready(self):
        """
        This runs ONCE when Django server starts.
        Initializes RAG service at startup.
        """
        # Prevent running during migrations
        import sys
        if 'migrate' in sys.argv or 'makemigrations' in sys.argv:
            return

        try:

            # Import here to avoid AppRegistryNotReady error
            from .rag_service import initialize_rag_service

            # Initialize RAG service (singleton - runs once)
            rag_service = initialize_rag_service()

            # Perform health check
            health = rag_service.health_check()

            if health['overall']:
                print("✅ RAG service initialized successfully and healthy!")
            else:
                print(f"⚠️  RAG service initialized with issues: {health}")
                if not health['pinecone']:
                    print("   → Pinecone issue: Check API key and index name")
                if not health['embedding_model']:
                    print("   → Embedding model issue: Check model name")
                if not health['llm']:
                    print("   → LLM issue: Will connect on first query")

            print("=" * 60)

        except Exception as e:
            print("error from apps.py")
            print(e)

