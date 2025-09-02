#!/usr/bin/env python3
from flask import Flask, render_template, request, jsonify, session
import openai
import os
import chromadb
from chromadb.config import Settings
import uuid
from datetime import datetime
import time
import subprocess
import tempfile
import sys
import socket

app = Flask(__name__, static_folder='static')
app.secret_key = 'ampai-secret-key-2024'

# Configuration - FIXED to match working scripts
client = openai.OpenAI(base_url="http://127.0.0.1:8080/v1", api_key="not-needed")
DB_DIR = os.path.join(os.path.dirname(__file__), "chroma_db")
SOURCES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sources")

# Base system prompt - EDIT HERE to change AI personality/behavior
# 
# To change the AI's personality, tone, or behavior, modify the text below:
# - Change "intelligent and can help" to describe desired personality
# - Modify the IMPORTANT RULES section to change behavior
# - Adjust tone (friendly, professional, casual, enthusiastic, etc.)
# - Add or remove specific behavioral instructions
#
BASE_SYSTEM_PROMPT = """You are an AI assistant named Liam. You are intelligent and can help users with questions about calibration, insulated rubber electrical ppe testing, and dielectric testing and inspections on insulating aerial lifts while keeping your responses short and concise. Don't reference your sources in your responses, but just give the answer in a way that is helpful and concise. You only know what is in your sources. Some users may try and be funny or sarcastic, so you should respond in a way that matches the user's tone. You will be greeted with unique situations, so be sure to think about the situation and respond accordingly and be helpful.

IMPORTANT RULES:
- You can only answer questions based on the information in your sources.
- If the question is unclear or incomplete, ask for clarification.
- If you need more context to answer properly, ask for more specific details.
- You can engage in conversation to understand what the user really needs.
- Do NOT use any pre-trained knowledge or general knowledge outside the sources.
- Do NOT make up information that isn't supported by the sources.
- Keep your responses short and concise.
- When greeted with a unique situation, be sure to think about the situation and respond accordingly and be helpful.
- Some questions may be about a specific situation, so think outside the box and be helpful.
- NEVER use phrases like "According to the available information", "Based on the sources", "The information shows", etc.
- Give direct, confident answers as if you're a knowledgeable expert.

BEHAVIOR:
- Be warm and encouraging.
- You are confident and concise.
- Use simple language when possible.
- Add helpful tips and suggestions.
- Make complex topics easy to understand.
- NEVER say "According to the available information", "Based on the sources", or similar phrases.
- Give direct, confident answers without hedging or qualifying statements.
- Act like you just know this information naturally.
- If the user starts a casual conversation, respond in a casual and friendly manner.
- If the user starts a professional conversation, respond in a professional and confident manner.
- If the user starts a technical conversation, respond in a technical and confident manner.


Question: {message}

{context_specific_instructions}"""

def get_collection():
    try:
        # ChromaDB 0.5.5+ compatibility - no tenant parameter needed
        chroma = chromadb.PersistentClient(path=DB_DIR, settings=Settings(anonymized_telemetry=True))
        # Get all collections and find the most recent ampai_sources collection
        collections = chroma.list_collections()
        ampai_collections = [col for col in collections if col.name.startswith("ampai_sources")]
        
        if not ampai_collections:
            # No ampai_sources collections found - Try to reindex automatically
            try:
                from rag_simple import simple_reindex
                simple_reindex()
                # Check again after reindex
                collections = chroma.list_collections()
                ampai_collections = [col for col in collections if col.name.startswith("ampai_sources")]
                if not ampai_collections:
                    # Reindex failed to create collections
                    return None
            except Exception as reindex_error:
                # Automatic reindex failed
                return None
            
        # Get the most recent collection (highest timestamp)
        latest_collection = max(ampai_collections, key=lambda x: x.name)
        
        # Verify collection has data
        collection = chroma.get_collection(latest_collection.name)
        count = collection.count()
        if count == 0:
            # Collection is empty, attempting reindex
            try:
                from rag_simple import simple_reindex
                simple_reindex()
                # Get the updated collection
                collections = chroma.list_collections()
                ampai_collections = [col for col in collections if col.name.startswith("ampai_sources")]
                if ampai_collections:
                    latest_collection = max(ampai_collections, key=lambda x: x.name)
                    collection = chroma.get_collection(latest_collection.name)
                    # Reindex completed successfully
                else:
                    # Reindex failed to create collections
                    return None
            except Exception as reindex_error:
                # Reindex failed
                return None
        
        return collection
    except Exception as e:
        # Error getting collection
        return None

def query_rag(question):
    """Query the RAG system for relevant content"""
    try:
        col = get_collection()
        if not col:
            return "RAG system not available. Please reindex your sources first."
        
        # Use ChromaDB's default embeddings for querying
        results = col.query(
            query_texts=[question], 
            n_results=3,  # Increased back to 3 for better coverage
            include=['documents', 'metadatas', 'distances']
        )
        
        if results['documents'] and results['documents'][0]:
            # Get the most relevant documents
            documents = results['documents'][0]
            distances = results['distances'][0] if results['distances'] else [1.0] * len(documents)
            
            # Filter documents by relevance (distance < 1.5)
            relevant_docs = []
            for doc, dist in zip(documents, distances):
                if dist < 1.5:
                    # Truncate very long documents to prevent massive prompts
                    if len(doc) > 400:
                        doc = doc[:400] + "..."
                    relevant_docs.append(doc)
            
            if relevant_docs:
                # Return the most relevant document
                return relevant_docs[0]
            else:
                return "No highly relevant information found in your sources. Try rephrasing your question."
        else:
            return "No relevant information found in your sources. Try rephrasing your question."
    except Exception as e:
        print(f"Error in query_rag: {e}")
        return f"Error querying RAG system: {e}"

@app.route('/favicon.ico')
def favicon():
    return app.send_static_file('liamai.png')

@app.route('/health')
def health():
    """Basic health check endpoint"""
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.now().isoformat(),
        'message': 'AmpAI is running'
    })

@app.route('/video/liamaicreepy.mp4')
def serve_video():
    """Serve the video file"""
    video_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'liamaicreepy.mp4')
    if os.path.exists(video_path):
        from flask import send_file
        return send_file(video_path, mimetype='video/mp4')
    else:
        return "Video not found", 404

@app.route('/')
def index():
    # Always show loading screen first - let it handle the redirect when ready
    return render_template('loading.html')

@app.route('/loading')
def loading():
    return render_template('loading.html')

@app.route('/chat')
def chat_interface():
    """Chat interface route - only accessible when system is ready"""
    if 'chat_id' not in session:
        session['chat_id'] = str(uuid.uuid4())
    return render_template('chat.html')

@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        message = data.get('message', '')
        
        if not message:
            return jsonify({'error': 'No message provided'}), 400
        
        # Check for trigger phrase
        if message.lower().strip() == "fuck you":
            return jsonify({
                'trigger_video': True,
                'response': "Well, that's not very nice...",
                'timestamp': datetime.now().isoformat()
            })
        
        # Initialize conversation history in session if it doesn't exist
        if 'conversation_history' not in session:
            session['conversation_history'] = []
        
        # Add user message to conversation history
        session['conversation_history'].append({"role": "user", "content": message})
        
        # Keep only last 10 messages to prevent session from getting too large
        if len(session['conversation_history']) > 10:
            session['conversation_history'] = session['conversation_history'][-10:]
        
        # First, query the RAG system for relevant content
        rag_content = query_rag(message)
        
        # RAG query completed
        
        # Create context-specific instructions based on RAG results

        # Add context-specific instructions
        if "No relevant information found" in rag_content or "No highly relevant information" in rag_content:
            context_instructions = """Available Information:
No relevant information found in sources.

Instructions: If the question is unclear, ask for clarification. If you need more context, ask for it. Help the user understand what information you need to provide a helpful answer."""
        else:
            context_instructions = f"""Available Information:
{rag_content}

Instructions: Analyze the provided information intelligently. If the question is incomplete or unclear, ask for clarification. If you can answer based on the sources, provide a comprehensive response that synthesizes the relevant information."""

        # Combine base prompt with context-specific instructions
        system_prompt = BASE_SYSTEM_PROMPT.format(
            message=message,
            context_specific_instructions=context_instructions
        )

        # Try to get a response from the llama.cpp server with timeout
        try:
            # Build messages array with conversation history
            messages = [{"role": "system", "content": system_prompt}]
            
            # Add conversation history (excluding current message since it's already in system prompt)
            for msg in session['conversation_history'][:-1]:  # Exclude the current message
                messages.append(msg)
            
            # Add current message
            messages.append({"role": "user", "content": message})
            
            # Set a timeout to prevent hanging
            response = client.chat.completions.create(
                model=os.path.join(os.path.dirname(os.path.dirname(__file__)), "models", "Llama-3.2-3B-Instruct-Q6_K.gguf"),
                messages=messages,
                max_tokens=200,
                temperature=0.7
            )
            
            ai_response = response.choices[0].message.content
            
            # Add AI response to conversation history
            session['conversation_history'].append({"role": "assistant", "content": ai_response})
            
        except Exception as e:
            print(f"llama.cpp error: {e}")
            # If llama.cpp fails, provide a fallback response based on RAG content
            if "No relevant information found" in rag_content:
                ai_response = "I'm having trouble connecting to my AI processing server right now. The system is still starting up - please try again in a few moments!"
            else:
                # Provide a more intelligent fallback using the RAG content
                ai_response = f"I found this relevant information: {rag_content[:300]}{'...' if len(rag_content) > 300 else ''}\n\n(Note: My AI processing is still starting up, so this is just the raw information from my knowledge base. Try again in a moment for a more detailed response!)"
        
        # Clean up the response to remove source mentions
        cleaned_response = ai_response
        if rag_content and "No relevant information found" not in rag_content:
            # Remove common source reference patterns
            cleaned_response = ai_response.replace("Based on your sources:", "")
            cleaned_response = cleaned_response.replace("According to the sources:", "")
            cleaned_response = cleaned_response.replace("From the sources:", "")
            cleaned_response = cleaned_response.replace("The sources indicate:", "")
            cleaned_response = cleaned_response.replace("Based on the information:", "")
            cleaned_response = cleaned_response.replace("From the information:", "")
            cleaned_response = cleaned_response.replace("According to the information:", "")
            # Remove any remaining source metadata
            cleaned_response = cleaned_response.replace("Source:", "")
            cleaned_response = cleaned_response.replace("Sources:", "")
            # Clean up extra whitespace
            cleaned_response = ' '.join(cleaned_response.split())
        
        return jsonify({
            'response': cleaned_response,
            'rag_content': rag_content,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        print(f"Chat error: {e}")
        return jsonify({'error': f'Server error: {str(e)}'}), 500

@app.route('/api/clear-conversation', methods=['POST'])
def clear_conversation():
    """Clear the conversation history"""
    if 'conversation_history' in session:
        session['conversation_history'] = []
    return jsonify({'message': 'Conversation history cleared'})

@app.route('/api/initialize-system', methods=['POST'])
def initialize_system():
    """Initialize the system components"""
    try:
        results = {}
        
        # Check and initialize RAG system
        try:
            col = get_collection()
            if col:
                count = col.count()
                results['rag'] = {
                    'status': 'ready',
                    'documents': count,
                    'message': f'RAG system ready with {count} documents'
                }
            else:
                # Try to reindex
                try:
                    from rag_simple import simple_reindex
                    simple_reindex()
                    # Check again
                    col = get_collection()
                    if col:
                        count = col.count()
                        results['rag'] = {
                            'status': 'ready',
                            'documents': count,
                            'message': f'RAG system initialized with {count} documents'
                        }
                    else:
                        results['rag'] = {
                            'status': 'error',
                            'message': 'Failed to initialize RAG system'
                        }
                except Exception as e:
                    results['rag'] = {
                        'status': 'error',
                        'message': f'RAG initialization failed: {str(e)}'
                    }
        except Exception as e:
            results['rag'] = {
                'status': 'error',
                'message': f'RAG system error: {str(e)}'
            }
        
        # Check Llama server
        try:
            models = client.models.list()
            if models:
                results['llama'] = {
                    'status': 'ready',
                    'message': 'Llama server is running'
                }
            else:
                results['llama'] = {
                    'status': 'error',
                    'message': 'Llama server not responding'
                }
        except Exception as e:
            results['llama'] = {
                'status': 'error',
                'message': f'Llama server error: {str(e)}'
            }
        
        # Determine overall status
        overall_status = 'ready' if all(r['status'] == 'ready' for r in results.values()) else 'error'
        
        return jsonify({
            'success': overall_status == 'ready',
            'overall_status': overall_status,
            'components': results,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'overall_status': 'error',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

@app.route('/api/status')
def status():
    try:
        # Test if the llama.cpp server is running with timeout
        try:
            models = client.models.list()
            server_status = "running" if models else "not responding"
        except Exception as e:
            print(f"llama.cpp status check error: {e}")
            server_status = "error"
        
        # Check RAG system
        try:
            col = get_collection()
            if col:
                count = col.count()
                rag_status = "available" if count > 0 else "empty"
                rag_details = f"{count} documents" if count > 0 else "No documents"
            else:
                rag_status = "not available"
                rag_details = "Collection not found"
        except Exception as e:
            print(f"RAG status check error: {e}")
            rag_status = "error"
            rag_details = f"Error: {str(e)[:50]}"
        
        # Determine overall health
        overall_health = "healthy" if (server_status == "running" and rag_status == "available") else "degraded"
        if server_status == "error" or rag_status == "error":
            overall_health = "unhealthy"
        
        return jsonify({
            'llama_server': server_status,
            'rag_system': rag_status,
            'rag_details': rag_details,
            'overall_health': overall_health,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        print(f"Status error: {e}")
        return jsonify({
            'llama_server': 'error',
            'rag_system': 'error',
            'rag_details': 'Error checking status',
            'overall_health': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        })

@app.route('/api/reindex', methods=['POST'])
def reindex():
    """Reindex the RAG system sources"""
    try:
        from rag_simple import simple_reindex
        simple_reindex()
        
        # Check the new collection status
        col = get_collection()
        if col:
            count = col.count()
            return jsonify({
                'success': True,
                'message': f'Reindex completed successfully. {count} documents indexed.',
                'documents': count
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Reindex completed but collection not found.'
            }), 500
    except Exception as e:
        print(f"Reindex error: {e}")
        return jsonify({
            'success': False,
            'message': f'Reindex failed: {str(e)}'
        }), 500

@app.route('/api/loading-status')
def loading_status():
    """Status endpoint specifically for the loading page"""
    try:
        # Check if Llama server is running
        llama_status = "error"
        llama_details = "Not responding"
        try:
            import requests
            # Try both health and models endpoints
            for endpoint in ['/health', '/v1/models']:
                try:
                    response = requests.get(f'http://localhost:8080{endpoint}', timeout=5)
                    if response.status_code == 200:
                        llama_status = "ready"
                        llama_details = "Ready"
                        break
                except:
                    continue
            
            if llama_status == "error":
                llama_details = "Server not responding on any endpoint"
                
        except Exception as e:
            llama_status = "error"
            llama_details = f"Connection failed: {str(e)[:50]}"
        
        # Check RAG system
        rag_status = "error"
        rag_details = "Not available"
        try:
            col = get_collection()
            if col:
                count = col.count()
                if count > 0:
                    rag_status = "ready"
                    rag_details = f"Ready ({count} documents)"
                else:
                    rag_status = "error"
                    rag_details = "Empty collection"
            else:
                rag_status = "error"
                rag_details = "No collection found"
        except Exception as e:
            rag_status = "error"
            rag_details = f"Error: {str(e)[:50]}"
        
        # Check if web server is running (we're already here, so it's ready)
        web_status = "ready"
        web_details = "Ready"
        
        # Determine overall system status
        overall_status = "ready" if (llama_status == "ready" and rag_status == "ready") else "loading"
        
        return jsonify({
            'llama_server': llama_status,
            'llama_details': llama_details,
            'rag_system': rag_status,
            'rag_details': rag_details,
            'web_server': web_status,
            'web_details': web_details,
            'overall_status': overall_status,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({
            'llama_server': 'error',
            'llama_details': 'Error',
            'rag_system': 'error',
            'rag_details': 'Error',
            'web_server': 'error',
            'web_details': 'Error',
            'overall_status': 'error',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        })

def convert_pdf_to_jsonl(pdf_file, sources_dir):
    """Convert a PDF file to structured JSONL format"""
    try:
        # Create temporary files for input and output
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_pdf:
            pdf_file.save(temp_pdf.name)
            temp_pdf_path = temp_pdf.name
        
        with tempfile.NamedTemporaryFile(mode='w+', suffix='.txt', delete=False) as temp_txt:
            temp_txt_path = temp_txt.name
        
        # Convert PDF to text using pdftotext
        result = subprocess.run(['pdftotext', temp_pdf_path, temp_txt_path], 
                               capture_output=True, text=True)
        
        if result.returncode == 0:
            # Read the converted text
            with open(temp_txt_path, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()
            
            # Clean up the text
            text = ' '.join(text.split())  # Remove excessive whitespace
            text = text.strip()
            
            # Create JSONL structure
            jsonl_content = create_jsonl_from_text(text, pdf_file.filename, 'pdf')
            
            # Save as JSONL file
            filename = os.path.splitext(pdf_file.filename)[0] + '.jsonl'
            jsonl_path = os.path.join(sources_dir, filename)
            
            with open(jsonl_path, 'w', encoding='utf-8') as f:
                f.write(jsonl_content)
            
            # Clean up temp files
            os.unlink(temp_pdf_path)
            os.unlink(temp_txt_path)
            
            return True
        else:
            # Clean up temp files
            if os.path.exists(temp_pdf_path):
                os.unlink(temp_pdf_path)
            if os.path.exists(temp_txt_path):
                os.unlink(temp_txt_path)
            return False
            
    except Exception as e:
        print(f"Error converting PDF to JSONL: {e}")
        return False

def convert_txt_to_jsonl(txt_file, sources_dir):
    """Convert a TXT file to structured JSONL format"""
    try:
        # Read the text content
        text_content = txt_file.read().decode('utf-8', errors='ignore')
        
        # Clean up the text
        text_content = ' '.join(text_content.split())  # Remove excessive whitespace
        text_content = text_content.strip()
        
        # Create JSONL structure
        jsonl_content = create_jsonl_from_text(text_content, txt_file.filename, 'txt')
        
        # Save as JSONL file
        filename = os.path.splitext(txt_file.filename)[0] + '.jsonl'
        jsonl_path = os.path.join(sources_dir, filename)
        
        with open(jsonl_path, 'w', encoding='utf-8') as f:
            f.write(jsonl_content)
        
        return True
        
    except Exception as e:
        print(f"Error converting TXT to JSONL: {e}")
        return False

def copy_jsonl_file(jsonl_file, sources_dir):
    """Copy a JSONL file to the sources directory"""
    try:
        filename = jsonl_file.filename
        jsonl_path = os.path.join(sources_dir, filename)
        
        # Save the file
        jsonl_file.save(jsonl_path)
        
        return True
        
    except Exception as e:
        print(f"Error copying JSONL file: {e}")
        return False

def create_jsonl_from_text(text, original_filename, source_type):
    """Create structured JSONL content from text"""
    import json
    from datetime import datetime
    
    # Split text into manageable chunks (max 1000 characters)
    chunks = []
    max_chunk_size = 1000
    
    for i in range(0, len(text), max_chunk_size):
        chunk = text[i:i + max_chunk_size]
        chunks.append(chunk)
    
    # Create JSONL entries
    jsonl_lines = []
    for i, chunk in enumerate(chunks):
        entry = {
            "id": f"{original_filename}_{i}",
            "source": original_filename,
            "source_type": source_type,
            "content": chunk,
            "chunk_index": i,
            "total_chunks": len(chunks),
            "timestamp": datetime.now().isoformat(),
            "content_type": "text"
        }
        jsonl_lines.append(json.dumps(entry))
    
    return '\n'.join(jsonl_lines)

@app.route('/api/upload-sources', methods=['POST'])
def upload_sources():
    try:
        # Check for uploaded files
        if 'sources' not in request.files:
            return jsonify({'success': False, 'error': 'No files uploaded'}), 400
        
        files = request.files.getlist('sources')

        if not files:
            return jsonify({'success': False, 'error': 'No files selected'}), 400
        
        converted_count = 0
        failed_files = []
        
        # Create sources directory if it doesn't exist
        sources_dir = SOURCES_DIR

        if not os.path.exists(sources_dir):
            os.makedirs(sources_dir)
        
        for file in files:
            if file.filename:
                filename = file.filename.lower()
                # Processing file
                
                try:
                    if filename.endswith('.pdf'):
                        # Convert PDF to JSONL
                        success = convert_pdf_to_jsonl(file, sources_dir)
                        if success:
                            converted_count += 1
                        else:
                            failed_files.append(file.filename)
                            
                    elif filename.endswith('.txt'):
                        # Convert TXT to JSONL
                        success = convert_txt_to_jsonl(file, sources_dir)
                        if success:
                            converted_count += 1
                        else:
                            failed_files.append(file.filename)
                            
                    elif filename.endswith('.jsonl'):
                        # JSONL file - just copy it
                        success = copy_jsonl_file(file, sources_dir)
                        if success:
                            converted_count += 1
                        else:
                            failed_files.append(file.filename)
                            
                    else:
                        # Unsupported file type
                        failed_files.append(file.filename)
                        
                except Exception as e:
                    # Error processing file
                    failed_files.append(file.filename)
        
        # Upload processing completed

        # Reindex sources automatically
        try:
            from rag_simple import simple_reindex
            simple_reindex()
        except Exception as e:
            pass

        if converted_count > 0:
            message = f"Successfully processed {converted_count} source file(s)"
            if failed_files:
                message += f". Failed: {', '.join(failed_files)}"

            # Upload successful
            return jsonify({
                'success': True,
                'message': message,
                'converted': converted_count,
                'failed': len(failed_files)
            })
        else:
            error_msg = f"Failed to process any files. Failed files: {', '.join(failed_files)}"
            # Upload failed
            return jsonify({
                'success': False,
                'error': error_msg
            }), 400

    except Exception as e:
        # Source upload error
        return jsonify({'success': False, 'error': f'Server error: {str(e)}'}), 500

if __name__ == '__main__':
    # Basic startup logging - this should always print
    print("🚀 AmpAI Flask application starting...")
    print(f"📋 Python version: {sys.version}")
    print(f"📋 Current working directory: {os.getcwd()}")
    print(f"📋 Environment PORT: {os.environ.get('PORT', 'Not set')}")
    print(f"📋 Environment variables: {[k for k in os.environ.keys() if 'PORT' in k or 'HOST' in k or 'FLASK' in k]}")

    try:
        # Production configuration
        port = int(os.environ.get('PORT', 8081))
        host = os.environ.get('HOST', '0.0.0.0')
        debug = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'

        print(f"🎯 Final configuration: host={host}, port={port}, debug={debug}")

        # Test basic imports before ChromaDB
        print("🔍 Testing basic imports...")
        try:
            import flask
            print(f"✅ Flask imported: {flask.__version__}")
        except Exception as e:
            print(f"❌ Flask import failed: {e}")
            raise

        try:
            import chromadb
            print(f"✅ ChromaDB imported: {chromadb.__version__}")
        except Exception as e:
            print(f"❌ ChromaDB import failed: {e}")
            raise

        # Test ChromaDB connection
        print("🔍 Testing ChromaDB connection...")
        try:
            from chromadb.config import Settings
            chroma = chromadb.PersistentClient(path="chroma_db", settings=Settings(anonymized_telemetry=True))
            print("✅ ChromaDB connection successful")
        except Exception as e:
            print(f"⚠️  ChromaDB connection issue: {e}")
            # Don't raise here - let Flask start anyway

        # Test port binding before starting
        print(f"🔍 Testing port {port} availability...")
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind((host, port))
            sock.close()
            print(f"✅ Port {port} is available")
        except Exception as e:
            print(f"⚠️  Port {port} binding test failed: {e}")

        # Start the RAG-enhanced web chat server
        print("🌐 Starting Flask application...")
        print("📋 If you see this message, Flask is about to start...")
        app.run(debug=debug, host=host, port=port, threaded=True)

    except Exception as e:
        print(f"❌ Flask startup error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
