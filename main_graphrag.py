import asyncio
import logging
from backend.rag.engines.vector_engine import VectorEngine
from backend.rag.engines.graph_engine import GraphEngine
from backend.rag.engines.neural_engine import NeuralEngine
from backend.rag.engines.symbolic_engine import SymbolicEngine
from backend.rag.enterprise_ai.orchestrator import EnterpriseAIOrchestrator

logging.basicConfig(level=logging.INFO)

async def main():
    print("="*80)
    print("🚀 VIRAL MARKETING - GRAPHRAG ENTERPRISE AI")
    print("="*80)
    
    # Initialize engines
    engines = {
        'vector': VectorEngine(vector_store=None),
        'graph': GraphEngine(graph_store=None, vector_engine=None),
        'neural': NeuralEngine(graph_engine=None, vector_engine=None),
        'symbolic': SymbolicEngine()
    }
    
    # Link engines
    engines['graph'].vector_engine = engines['vector']
    engines['neural'].graph = engines['graph']
    engines['neural'].vector = engines['vector']
    
    # Create enterprise orchestrator
    enterprise = EnterpriseAIOrchestrator(engines)
    
    # Example queries
    queries = [
        "Analyze Q4 luxury chocolate campaign performance",
        "Recommend audience targeting for premium products",
        "Optimize budget allocation across channels"
    ]
    
    for query in queries:
        print(f"\n📊 Query: {query}")
        result = await enterprise.process_business_request(query)
        print(f"✅ Status: {result['status']}")
        print(f"📈 Results: {result['results']}")
        print(f"💡 Recommendations:")
        for rec in result['recommendations']:
            print(f"   • {rec}")
        print("-"*80)

if __name__ == "__main__":
    asyncio.run(main())
