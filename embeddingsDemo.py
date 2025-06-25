from sentence_transformers import SentenceTransformer
import csv
import numpy as np

# 1. Load a pretrained Sentence Transformer model
model = SentenceTransformer("all-mpnet-base-v2")

#read the csv file
with open('Expanded_Sample_Inventory.csv', 'r') as file:
    reader = csv.reader(file)
    compNames = [row[0] for row in reader][1:]
    compQuantities = [row[1] for row in reader][1:]

print(f"Computing Embeddings for {len(compNames)} components")


# 2. Calculate embeddings by calling model.encode()
embeddings = model.encode(compNames)

# 3. Calculate the embedding similarities
similarities = model.similarity(embeddings, embeddings)

while True:
    userInput = input("Enter a component name: ")
    if userInput == "exit":
        break
    else:
        userEmbedding = model.encode([userInput])
        similarities = model.similarity(userEmbedding, embeddings).squeeze()
        mostSimilarIndex = np.argmax(similarities).item()
        print(similarities.shape)
        print(mostSimilarIndex)
        print(f"Most similar component: {compNames[mostSimilarIndex]}")
        print(f"Similarity: {similarities[mostSimilarIndex]}")