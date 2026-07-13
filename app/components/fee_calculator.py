import streamlit as st
from app.services.fee_service import BVRITFeeService
from app.rag.generator import RAGGenerator

def render_fee_calculator(generator: RAGGenerator | None = None):
    """Renders the BVRIT Fee Calculator view with premium UI elements."""
    
    # Modern Glassmorphism Styling Injection
    st.markdown("""
        <style>
        .glass-card {
            background: rgba(255, 255, 255, 0.05);
            backdrop-filter: blur(10px);
            -webkit-backdrop-filter: blur(10px);
            border-radius: 16px;
            border: 1px solid rgba(255, 255, 255, 0.1);
            padding: 24px;
            margin-bottom: 20px;
        }
        .savings-card {
            background: rgba(40, 167, 69, 0.12);
            border: 1px solid rgba(40, 167, 69, 0.3);
            border-radius: 12px;
            padding: 15px;
            color: #28a745;
            font-weight: 600;
        }
        .payable-card {
            background: rgba(0, 123, 255, 0.1);
            border: 1px solid rgba(0, 123, 255, 0.25);
            border-radius: 12px;
            padding: 20px;
            text-align: center;
            margin-top: 15px;
        }
        .payable-value {
            font-size: 2.2rem;
            font-weight: 700;
            color: #007bff;
        }
        </style>
    """, unsafe_allow_html=True)

    # Header / Description Section
    st.title("🧮 BVRIT Fee Calculator")
    st.markdown(
        "*BVRIT Fee Calculator helps students estimate their total educational expenses by combining "
        "tuition fees, hostel charges, and applicable scholarship discounts using fee information available "
        "in the BVRIT knowledge base.*"
    )
    st.write("---")

    # Initialize Service Layer — wire in the live RAG generator
    fee_service = BVRITFeeService(rag_pipeline=generator)

    # Layout: Interactive Controls Panel
    with st.container():
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        st.subheader("Configure Parameters")
        
        col1, col2 = st.columns(2)
        with col1:
            branch = st.selectbox(
                "Select Academic Branch",
                ["Computer Science & Engineering (CSE)", "Information Technology (IT)", 
                 "Electronics & Communication (ECE)", "Electrical & Electronics (EEE)", 
                 "Mechanical Engineering (ME)", "Civil Engineering (CE)"]
            )
            years = st.slider("Number of Academic Years", min_value=1, max_value=4, value=4)

        with col2:
            include_hostel = st.toggle("Opt for Hostel Accommodation", value=False)
            include_transport = st.toggle("Opt for College Transport", value=False)
            scholarship_pct = st.slider("Scholarship Award Percentage (%)", min_value=0, max_value=100, value=0, step=5)
        
        st.markdown('</div>', unsafe_allow_html=True)

    # Execution and Validation Engine
    fee_info = fee_service.fetch_fee_details(branch)

    if not fee_info["success"]:
        st.error("⚠️ Fee information for this selection is not available in the knowledge base.")
        return

    # Perform calculations in real-time
    metrics = fee_service.calculate_fees(
        fee_info=fee_info,
        years=years,
        include_hostel=include_hostel,
        include_transport=include_transport,
        scholarship_pct=scholarship_pct
    )

    # Output Presentation Section
    st.subheader("Estimated Cost Breakdown")
    
    m_col1, m_col2, m_col3 = st.columns(3)
    with m_col1:
        st.metric("Annual Tuition Fee", f"₹{metrics['annual_tuition']:,.2f}")
        st.metric("Total Tuition Base", f"₹{metrics['total_tuition']:,.2f}")
    with m_col2:
        st.metric("Hostel Charges Accrued", f"₹{metrics['hostel_total']:,.2f}")
        st.metric("Transport Charges Accrued", f"₹{metrics['transport_total']:,.2f}")
    with m_col3:
        st.metric("Other & Misc Charges", f"₹{metrics['other_charges']:,.2f}")
        st.metric("Gross Total Sum", f"₹{metrics['grand_total']:,.2f}")

    # Premium Summary Highlight Blocks
    st.markdown("---")
    res_col1, res_col2 = st.columns(2)
    
    with res_col1:
        if metrics['scholarship_amount'] > 0:
            st.markdown(f"""
                <div class="savings-card">
                    🎉 Scholarship Savings<br/>
                    <span style="font-size: 1.5rem;">- ₹{metrics['scholarship_amount']:,.2f}</span>
                    <p style="font-size: 0.85rem; margin: 5px 0 0 0; font-weight: normal;">
                        Applied ({scholarship_pct}%) savings to standard base tuition charges.
                    </p>
                </div>
            """, unsafe_allow_html=True)
        else:
            st.info("No scholarship percentages applied yet. Adjust the configuration slider above to calculate discounts.")

    with res_col2:
        st.markdown(f"""
            <div class="payable-card">
                <span style="text-transform: uppercase; font-size: 0.85rem; letter-spacing: 1px; color: #555;">Final Net Payable Amount</span><br/>
                <span class="payable-value">₹{metrics['final_payable']:,.2f}</span>
            </div>
        """, unsafe_allow_html=True)

    # Reset / Control Block
    st.write("")
    if st.button("Reset Calculation Parameters", type="secondary"):
        st.rerun()

    # Verified Knowledge Base Citation Block
    st.write("---")
    with st.expander("📄 Source Information & Citations", expanded=False):
        st.caption("The exact figures surfaced above were derived dynamically from the following document sections:")
        for doc in fee_info["sources"]:
            st.markdown(f"- ✔️ `{doc}`")