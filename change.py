b = []
with open(r'C:\Users\mishr\OneDrive\Desktop\NeuralDecipher\data\uga-heb.small.no_spe.cog') as f:
    for line in f:
        a = line.strip().split("\t")
        b.append([a[1], a[0]])


with open(r'C:\Users\mishr\OneDrive\Desktop\NeuralDecipher\data\heb-uga.small.no_spe.cog.txt', 'w') as f:
    f.writelines('\t'.join(l) + '\n' for l in b)