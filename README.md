# MESA (Medical entity Extraction with Schema Alignment)

## Overview

MESA standardises free-text patient data under a schema of choice, in order to enable downstream activities such as analytics and clinical trial recruitment.

<p align="center">
  <img src="_assets/overview.svg" width="700" alt="MESA overview diagram">
</p>

### Components

MESA consists of a number of different components that work together in order to standardise data:

1. Docsynth leverages an understanding of the structure of the real free-text data to build a synthetic corpus that emulates a wide range of possible real documents. 
This corpus is built using a large foundation model.

2. Datagen passes each of these synthetic documents to a foundation model, along with a custom schema containing target fields of interest (derived from domain knowledge). The model is prompted to standardise each document to the schema, creating a set of pairs illustrating the standardisation process.

3. Finetune uses these pairs to train a smaller, open source model.

4. Deploy provides an environment in which these fine-tuned models can be used for inference against the real documents.

<p align="center">
  <img src="_assets/components.svg" width="600" alt="MESA overview diagram">
</p>

This repository contains a notebook for each component, illustrating the standardisation process in practice.
