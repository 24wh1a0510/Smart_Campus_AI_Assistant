import re
from typing import Dict, Any, Optional, List

# Target exact imports from your existing 'rag' folder as needed
# e.g., from app.rag.query_engine import custom_rag_query 

class BVRITFeeService:
    """Service layer to interface with the existing RAG vector database 
    and compute educational expenses for BVRIT."""
    
    def __init__(self, rag_pipeline: Optional[Any] = None):
        """
        Pass your existing RAG pipeline/vector store instance here if needed,
        or use a singleton import inside the methods.
        """
        self.rag_pipeline = rag_pipeline

    def _query_rag_kb(self, query: str) -> Dict[str, Any]:
        """
        Queries the live RAG vector store using the injected RAGGenerator.
        Falls back to a safe empty result if the pipeline is unavailable.
        """
        if self.rag_pipeline is not None:
            try:
                response = self.rag_pipeline.answer(question=query, history=[], top_k=6)
                sources = [c.source for c in response.citations] if response.citations else ["BVRIT Knowledge Base"]
                return {
                    "text": response.answer,
                    "sources": sources,
                }
            except Exception:
                pass  # Fall through to empty result on any error

        # Pipeline not available — return empty so fetch_fee_details() reports failure
        return {"text": "", "sources": []}

    def _extract_number(self, text: str, regex_pattern: str) -> Optional[float]:
        """Extracts numerical fee value from RAG text using regex."""
        match = re.search(regex_pattern, text, re.IGNORECASE)
        if match:
            # Clean commas, currency symbols, and spaces out
            raw_val = match.group(1).replace(",", "").replace(" ", "").replace("₹", "").replace("Rs.", "").replace("INR", "")
            try:
                return float(raw_val)
            except ValueError:
                return None
        return None

    def _extract_all_numbers(self, text: str, regex_pattern: str) -> List[float]:
        """Extracts all matching numerical values for summing multiple line items."""
        results = []
        for match in re.finditer(regex_pattern, text, re.IGNORECASE):
            raw_val = match.group(1).replace(",", "").replace(" ", "")
            try:
                results.append(float(raw_val))
            except ValueError:
                pass
        return results

    def fetch_fee_details(self, branch: str) -> Dict[str, Any]:
        """
        Queries the knowledge base for specific branch, hostel, and transport fees.
        Handles ₹ symbol format returned by the RAG (e.g., ₹1,20,000/year).
        """
        query = f"What are the official fees for {branch} including tuition, hostel, transport, and other charges?"
        rag_result = self._query_rag_kb(query)
        text = rag_result.get("text", "")
        sources = rag_result.get("sources", ["BVRIT Knowledge Base Docs"])

        # Matches: "Tuition Fee: ₹1,20,000" or "tuition fee ₹1,20,000/year"
        tuition = self._extract_number(text, r"tuition\s*fee[:\s]*₹?([\d,]+)")

        # Hostel: "Hostel Fee: ₹85,000" or "hostel charges ₹85,000"
        hostel = self._extract_number(text, r"hostel[\w\s]*[:\s]*₹?([\d,]+)")

        # Transport/bus fee
        transport = self._extract_number(text, r"(?:transport|bus)\s*fee[:\s]*₹?([\d,]+)")

        # Sum all misc line items: NBA Fee, JNTUH Fee, Miscellaneous Fee, etc.
        # These appear as separate lines like "NBA Fee: ₹3,000/year"
        misc_items = self._extract_all_numbers(
            text,
            r"(?:nba|jntuh|miscellaneous|misc|university|special)\s*(?:fee|charges?)[:\s/\w]*₹?([\d,]+)"
        )
        other = sum(misc_items) if misc_items else 0.0

        return {
            "annual_tuition": tuition,
            "annual_hostel": hostel if hostel else 0.0,
            "annual_transport": transport if transport else 0.0,
            "other_charges": other,
            "sources": sources,
            "success": tuition is not None
        }

    def calculate_fees(self, 
                       fee_info: Dict[str, Any], 
                       years: int, 
                       include_hostel: bool, 
                       include_transport: bool, 
                       scholarship_pct: float) -> Dict[str, float]:
        """Applies exact system formulas cleanly with type safety."""
        annual_tuition = fee_info.get("annual_tuition", 0.0) or 0.0
        annual_hostel = fee_info.get("annual_hostel", 0.0) or 0.0
        annual_transport = fee_info.get("annual_transport", 0.0) or 0.0
        other_charges = fee_info.get("other_charges", 0.0) or 0.0

        total_tuition = annual_tuition * years
        hostel_total = (annual_hostel * years) if include_hostel else 0.0
        transport_total = (annual_transport * years) if include_transport else 0.0
        actual_other_charges = other_charges * years # Applied scale over duration

        scholarship_amount = (total_tuition * scholarship_pct) / 100.0
        
        grand_total = total_tuition + hostel_total + transport_total + actual_other_charges
        final_payable = grand_total - scholarship_amount

        return {
            "annual_tuition": annual_tuition,
            "total_tuition": total_tuition,
            "hostel_total": hostel_total,
            "transport_total": transport_total,
            "other_charges": actual_other_charges,
            "scholarship_amount": scholarship_amount,
            "grand_total": grand_total,
            "final_payable": final_payable
        }