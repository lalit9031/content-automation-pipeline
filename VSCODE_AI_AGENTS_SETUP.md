# VS Code AI Agents Setup Guide

This guide provides a step-by-step walkthrough to configure both **Continue** (for free local autocomplete/chat) and **Roo Code** (for autonomous agent coding using local Ollama & cloud AWS Bedrock Claude) inside Visual Studio Code.

---

## 📋 Prerequisites

1. **Ollama Setup**:
   * Download and install **Ollama** from [ollama.com](https://ollama.com/).
   * Open a terminal on your Windows machine and pull the local coding models:
     ```bash
     ollama pull qwen2.5-coder:14b
     ollama pull qwen2.5vl:latest
     ```

2. **AWS Bedrock Access Key**:
   Have your Amazon Bedrock Access Key ID and Secret Access Key ready. Ensure you have enabled **Claude model access** in your AWS console (under `ap-southeast-2` region).

---

## 1. 🤖 Continue Extension Setup (100% Free Local Chat & Autocomplete)

The **Continue** extension provides inline code completion (`Ctrl + I`) and a developer chat window (`Ctrl + L`) running fully locally on your GPU.

### **Step 1: Install the Extension**
* In VS Code, open the Extensions tab (`Ctrl + Shift + X`).
* Search for **Continue** and click **Install**.

### **Step 2: Write the Configuration**
Create or edit the file at **`C:\Users\user\.continue\config.yaml`** and paste the following configuration:

```yaml
name: Main Config
version: 1.0.0
schema: v1
models:
  - name: Qwen2.5-Coder (14B)
    provider: ollama
    model: qwen2.5-coder:14b
    roles:
      - chat
      - edit
      - autocomplete
  - name: Qwen2.5-VL (7B)
    provider: ollama
    model: qwen2.5vl:latest
    roles:
      - chat
```

### **Step 3: Save & Reload**
* Press **`Ctrl + Shift + P`** in VS Code.
* Select **`Developer: Reload Window`** and press **Enter**.
* Click the model selector pill in the chat input box and select **`Qwen2.5-Coder (14B)`**.

---

## 2. 🦘 Roo Code Setup (Autonomous Developer Agent - Local & Cloud Bedrock)

**Roo Code** is an autonomous agent that can read files, write code, run terminal commands, and browse the web (asking for your approval before execution).

### **Step 1: Install the Extension**
* In VS Code, search for **Roo Code** (Extension ID: `rooveterinaryinc.roo-cline`) and click **Install**.
* Reload the window (`Ctrl + Shift + P` -> `Developer: Reload Window`).
* Click the **Kangaroo icon** in the left-hand sidebar to open Roo Code.

### **Step 2: Configure the Local Profile (Free & Offline)**
* Click the **Gear icon** (Settings) at the top of the Roo Code panel.
* Set the settings as follows:
  * **API Provider**: `Ollama`
  * **Model**: `qwen2.5-coder:14b`
  * **Base URL**: `http://localhost:11434` (leave default)
* Click **Finish →**. 
* This configuration profile is named **`default`**.

### **Step 3: Configure the Bedrock Profile (Claude 4.6)**
* Click the **Gear icon** (Settings) at the top of the Roo Code panel.
* Click the **`+`** icon next to **Configuration Profile** to create a new profile and name it **`Bedrock`**.
* Set the settings as follows:
  * **API Provider**: `Amazon Bedrock`
  * **Authentication Method**: `AWS Credentials`
  * **AWS Access Key ID**: *Your IAM Access Key ID*
  * **AWS Secret Access Key**: *Your IAM Secret Access Key*
  * **AWS Region**: `ap-southeast-2` (Sydney)
  * **AWS Session Token**: `Leave Empty`
  * **Use global inference**: `Unchecked` (Disabled)
  * **Use cross-region inference**: `Unchecked` (Disabled)
  * **Enable prompt caching**: `Checked` (Enabled) ✅ *Saves up to 90% in token costs*
  * **Enable 1M context window**: `Unchecked` (Disabled)
  * **Use custom VPC endpoint**: `Unchecked` (Disabled)
  * **Model**: Select `anthropic.claude-sonnet-4-6` (or `anthropic.claude-3-5-sonnet-20241022-v2:0` as fallback).
  * **Enable reasoning**: `Unchecked` (Disabled) *Keeps model faster and cheaper*
* Click **Save** / click the back arrow **`← Settings`**.

---

## 🔄 Switching Profiles in Roo Code
* Click the **Gear icon** in the Roo Code panel.
* Under the **Configuration Profile** dropdown at the top:
  * Select **`default`** to use your free local GPU-accelerated model.
  * Select **`Bedrock`** to switch to the cloud-hosted Claude 4.6 model.
